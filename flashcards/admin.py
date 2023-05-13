from django.contrib import admin
from flashcards.models import SavedWord, Flashcard, Review
# Register your models here.

class FlashcardAdmin(admin.ModelAdmin):
    list_display = ('user', 'word', 'date_added', 'due',)

admin.site.register(SavedWord)
admin.site.register(Flashcard, FlashcardAdmin)
admin.site.register(Review)