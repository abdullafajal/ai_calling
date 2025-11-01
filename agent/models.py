from django.db import models

class Call(models.Model):
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

class Transcript(models.Model):
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name='transcripts')
    text = models.TextField()
    is_user = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)