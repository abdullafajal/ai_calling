from django.contrib import admin

from agent.models import Call, Transcript

# Register your models here.

admin.site.site_header = "AI Call Agent Admin"
admin.site.site_title = "AI Call Agent Admin Portal"
admin.site.index_title = "Welcome to the AI Call Agent Administration"

# You can register your models here if you have any, for example:
# from .models import YourModel
# admin.site.register(YourModel)    
from django.contrib import admin
from .models import Call, Transcript

# Inline transcript display within the Call admin
class TranscriptInline(admin.TabularInline):
    model = Transcript
    extra = 0  # no extra blank rows
    readonly_fields = ('text', 'is_user', 'timestamp')
    can_delete = False
    ordering = ('timestamp',)
    show_change_link = False

    def get_queryset(self, request):
        # Order by timestamp ascending
        qs = super().get_queryset(request)
        return qs.order_by('timestamp')


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ('id', 'start_time', 'end_time', 'duration')
    inlines = [TranscriptInline]
    readonly_fields = ('start_time', 'end_time')
    ordering = ('-start_time',)
    search_fields = ('id',)
    list_filter = ('start_time',)

    def duration(self, obj):
        if obj.end_time:
            return obj.end_time - obj.start_time
        return "Ongoing"
    duration.short_description = "Duration"


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ('id', 'call', 'is_user', 'short_text', 'timestamp')
    readonly_fields = ('call', 'text', 'is_user', 'timestamp')
    ordering = ('-timestamp',)
    list_filter = ('is_user',)
    search_fields = ('text',)

    def short_text(self, obj):
        return (obj.text[:60] + "...") if len(obj.text) > 60 else obj.text
    short_text.short_description = "Message"
