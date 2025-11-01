# AI Call Agent

This is a Django web app that allows users to make a simulated AI phone call directly in their browser.

## Features

- Real-time voice conversation with an AI agent.
- Support for multiple languages (English and Hindi).
- Selectable voice tones (male and female).
- Call transcripts are saved to the database.

## Getting Started

### Prerequisites

- Python 3.13 or later
- uv

### Installation

1.  Clone the repository:
    ```sh
    git clone https://github.com/abdullafajal/ai_calling.git
    ```
2.  Navigate to the project directory:
    ```sh
    cd ai_calling
    ```
3.  Install the dependencies:
    ```sh
    uv pip install -r requirements.txt
    ```
4.  Run the development server:
    ```sh
    python manage.py runserver
    ```

## Future Enhancements

- **Emotion-based responses**: The AI agent could respond with different emotions based on the user's input. This would require more advanced prompt engineering and possibly a different Gemini model.
- **Streaming speech output**: The AI's response could be streamed to the frontend as it's being generated, reducing the perceived latency.
- **Mobile optimization**: The UI could be optimized for a better experience on mobile devices.