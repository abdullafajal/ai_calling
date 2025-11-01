import json
import os
import asyncio
import speech_recognition as sr
from channels.generic.websocket import AsyncWebsocketConsumer
from gtts import gTTS
import google.generativeai as genai
from .models import Call, Transcript
from django.utils import timezone
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
import wave
from pydub import AudioSegment
from django.conf import settings

genai.configure(api_key=settings.GENAI_API_KEY)

def get_ai_response(prompt):
    """Get AI response from Gemini with faster settings"""
    print(f"[AI] Getting response for prompt: {prompt[:100]}...")
    try:
        model = genai.GenerativeModel(
            "gemini-flash-latest",
        )
        response = model.generate_content(prompt)
        print(f"[AI] Response generated: {response.text[:100]}...")
        return response.text
    except Exception as e:
        print(f"[AI ERROR] Failed to get response: {str(e)}")
        return "I'm sorry, I couldn't process that. Could you please try again?"


class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("[WebSocket] Connection attempt received")
        await self.accept()
        print("[WebSocket] Connection accepted")
        
        self.audio_buffer = bytearray()
        self.conversation_history = []
        self.is_processing = False
        
        os.makedirs("temp", exist_ok=True)
        os.makedirs("media", exist_ok=True)
        print("[FileSystem] Temp and media directories ensured")
        
        self.call = await database_sync_to_async(Call.objects.create)()
        print(f"[Database] Call created with ID: {self.call.id}")
        
        query_string = self.scope.get('query_string', b'').decode()
        print(f"[WebSocket] Query string: {query_string}")
        params = parse_qs(query_string)
        self.language = params.get('language', ['en'])[0]
        self.voice = params.get('voice', ['female'])[0]
        self.speed = float(params.get('speed', ['1.3'])[0])  # Speed multiplier
        print(f"[Config] Language: {self.language}, Voice: {self.voice}, Speed: {self.speed}")
        
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': 'Connected to AI Call Agent',
            'language': self.language,
            'voice': self.voice,
            'speed': self.speed
        }))
        print("[WebSocket] Connection confirmation sent to client")

    async def disconnect(self, close_code):
        print(f"[WebSocket] Disconnecting with code: {close_code}")
        self.call.end_time = timezone.now()
        await database_sync_to_async(self.call.save)()
        print(f"[Database] Call {self.call.id} ended and saved")

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            print(f"[WebSocket] Received text data: {text_data[:100]}")
            try:
                data = json.loads(text_data)
                if data.get('end_of_speech'):
                    print("[Audio] End of speech signal received")
                    if not self.is_processing and len(self.audio_buffer) > 0:
                        print("[Audio] Starting audio processing...")
                        await self.process_audio()
                    else:
                        print(f"[Audio] Skipping - is_processing={self.is_processing}, buffer_size={len(self.audio_buffer)}")
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse JSON: {str(e)}")
                
        elif bytes_data:
            bytes_length = len(bytes_data)
            self.audio_buffer.extend(bytes_data)
            print(f"[Audio] Received {bytes_length} bytes (WAV), buffer size: {len(self.audio_buffer)} bytes")

    async def process_audio(self):
        print(f"[Audio] Processing audio buffer of {len(self.audio_buffer)} bytes")
        
        if not self.audio_buffer or len(self.audio_buffer) < 1000:
            print("[Audio] Buffer is empty or too small, skipping processing")
            self.audio_buffer = bytearray()
            return

        self.is_processing = True
        
        try:
            current_audio = bytes(self.audio_buffer)
            buffer_size = len(current_audio)
            self.audio_buffer = bytearray()
            print(f"[Audio] Saved {buffer_size} bytes, buffer cleared for new audio")

            wav_path = os.path.join("temp", f"temp_audio_{self.call.id}.wav")
            print(f"[Audio] Writing WAV to: {wav_path}")
            
            with open(wav_path, "wb") as f:
                f.write(current_audio)
            
            file_size = os.path.getsize(wav_path)
            print(f"[Audio] WAV file size on disk: {file_size} bytes")
            
            if file_size < 1000:
                raise Exception(f"Audio file too small: {file_size} bytes")

            # Verify it's a valid WAV file
            try:
                with wave.open(wav_path, 'rb') as wf:
                    print(f"[Audio] WAV format: {wf.getnchannels()} channels, {wf.getframerate()} Hz, {wf.getnframes()} frames")
            except Exception as wav_error:
                print(f"[Audio] WAV validation error: {wav_error}")

            # Convert audio to text
            print("[Speech Recognition] Starting speech recognition...")
            text = await asyncio.get_event_loop().run_in_executor(
                None,
                self._recognize_speech,
                wav_path
            )

            if text:
                print(f"[Speech Recognition] Recognized text: {text}")
                await self.send(text_data=json.dumps({
                    'transcript': f'{text}',
                    'sender': 'user'
                }))
                
                await database_sync_to_async(Transcript.objects.create)(
                    call=self.call,
                    text=text,
                    is_user=True
                )
                print("[Database] User transcript saved")

                self.conversation_history.append(f"User: {text}")

                print("[AI] Preparing prompt for AI...")
                # Add instruction for more natural, concise responses
                system_instruction = "You are a helpful AI assistant in a phone conversation. Keep responses brief, natural, and conversational (2-3 sentences max). Speak like a human would in a phone call."
                prompt = system_instruction + "\n\n" + "\n".join(self.conversation_history[-5:])
                
                ai_response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    get_ai_response,
                    prompt
                )

                self.conversation_history.append(f"AI: {ai_response}")
                print(f"[AI] AI Response: {ai_response[:100]}...")

                await self.send(text_data=json.dumps({
                    'transcript': f'{ai_response}',
                    'sender': 'ai'
                }))
                
                await database_sync_to_async(Transcript.objects.create)(
                    call=self.call,
                    text=ai_response,
                    is_user=False
                )
                print("[Database] AI transcript saved")

                print("[TTS] Converting AI response to speech...")
                audio_response_path = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._text_to_speech,
                    ai_response
                )
                print(f"[TTS] Audio saved to: {audio_response_path}")

                audio_url = f'/media/response_{self.call.id}.mp3'
                await self.send(text_data=json.dumps({
                    'audio_url': audio_url
                }))
                print(f"[WebSocket] Audio URL sent to client: {audio_url}")
            else:
                print("[Speech Recognition] No text recognized")
                await self.send(text_data=json.dumps({
                    'transcript': 'Could not understand audio. Please speak clearly.',
                    'sender': 'system'
                }))

            print("[FileSystem] Cleaning up temporary files...")
            if os.path.exists(wav_path):
                os.remove(wav_path)
                print(f"[FileSystem] Removed: {wav_path}")

        except Exception as e:
            print(f"[ERROR] Error processing audio: {str(e)}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            await self.send(text_data=json.dumps({
                'transcript': f'Error processing audio: {str(e)}',
                'sender': 'system',
                'error': True
            }))
        finally:
            self.is_processing = False
            print("[Audio] Processing complete, ready for new audio")

    def _recognize_speech(self, wav_path):
        """Recognize speech from audio file (runs in thread pool)"""
        print(f"[Speech Recognition] Processing file: {wav_path}")
        r = sr.Recognizer()
        
        # Optimized for faster recognition
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True
        r.pause_threshold = 0.6  # Reduced for faster response
        
        try:
            with sr.AudioFile(wav_path) as source:
                print("[Speech Recognition] Reading audio file...")
                r.adjust_for_ambient_noise(source, duration=0.3)  # Faster adjustment
                audio_data = r.record(source)
                print(f"[Speech Recognition] Audio data length: {len(audio_data.frame_data)} bytes")
                
                print(f"[Speech Recognition] Recognizing with language: {self.language}")
                text = r.recognize_google(audio_data, language=self.language)
                print(f"[Speech Recognition] Success! Text: {text}")
                return text
                
        except sr.UnknownValueError:
            print("[Speech Recognition] Could not understand audio")
            return None
        except sr.RequestError as e:
            print(f"[Speech Recognition ERROR] Request error: {str(e)}")
            return None
        except Exception as e:
            print(f"[Speech Recognition ERROR] Unexpected error: {str(e)}")
            import traceback
            print(f"[Speech Recognition ERROR] Traceback: {traceback.format_exc()}")
            return None

    def _text_to_speech(self, text):
        """Convert text to speech with better voice quality and speed (runs in thread pool)"""
        print(f"[TTS] Converting text to speech: {text[:50]}...")
        try:
            # Select better voice options for more natural sound
            lang_code = self.language
            tld = 'com'  # Default
            
            if self.language == 'en':
                if self.voice == 'male':
                    lang_code = 'en'
                    tld = 'co.uk'  # British male voice (more natural)
                else:
                    lang_code = 'en'
                    tld = 'com.au'  # Australian female voice (clearer)
            elif self.language == 'hi':
                lang_code = 'hi'
                tld = 'co.in'  # Indian voices

            # Generate speech with gTTS
            tts = gTTS(text=text, lang=lang_code, tld=tld, slow=False)
            temp_path = os.path.join("temp", f"temp_response_{self.call.id}.mp3")
            tts.save(temp_path)
            print(f"[TTS] Initial audio saved to: {temp_path}")
            
            # Speed up the audio using pydub
            audio = AudioSegment.from_mp3(temp_path)
            
            # Speed up audio (1.3x = 30% faster, sounds more natural than higher speeds)
            speed_factor = self.speed
            spedup_audio = audio.speedup(playback_speed=speed_factor)
            
            # Optional: Slightly increase pitch to compensate for speed (makes it sound more natural)
            # Uncomment if you want pitch adjustment
            # spedup_audio = spedup_audio._spawn(spedup_audio.raw_data, overrides={
            #     "frame_rate": int(spedup_audio.frame_rate * 1.1)
            # }).set_frame_rate(spedup_audio.frame_rate)
            
            # Save final audio
            audio_response_path = os.path.join("media", f"response_{self.call.id}.mp3")
            spedup_audio.export(audio_response_path, format="mp3", bitrate="128k")
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            print(f"[TTS] Spedup audio ({speed_factor}x) saved successfully to: {audio_response_path}")
            return audio_response_path
            
        except Exception as e:
            print(f"[TTS ERROR] Failed to convert text to speech: {str(e)}")
            # Fallback to regular TTS without speed adjustment
            try:
                tts = gTTS(text=text, lang=self.language, slow=False)
                audio_response_path = os.path.join("media", f"response_{self.call.id}.mp3")
                tts.save(audio_response_path)
                print(f"[TTS] Fallback audio saved to: {audio_response_path}")
                return audio_response_path
            except Exception as fallback_error:
                print(f"[TTS ERROR] Fallback also failed: {str(fallback_error)}")
                raise