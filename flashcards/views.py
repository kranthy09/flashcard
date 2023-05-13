import json
from datetime import timedelta
from django.utils import timezone
from datetime import datetime
from django.middleware.csrf import get_token
from django.core import serializers
from django.http import JsonResponse
from django.views import View
from flashcards.models import Flashcard, SavedWord, Review


# Create your views here.

class FlashcardView(View):
    MAX_NEW_CARDS = 10
    MAX_TOTAL_CARDS = 15

    def get(self, request):
        """Returns the list of Flashcard objects to be studied today.
        Details can be found in the technical spec."""
        cards = []
        new_cards = []
        now = datetime.now()
        # create 10 cards for the day
        cards_created_today = \
            Flashcard.objects.filter(
                user=request.user,
                date_added__date=now)
        cards_created_today_count = cards_created_today.count()
        if cards_created_today_count < 10:
            free_saved_words = \
                SavedWord.objects.exclude(
                    id__in=Flashcard.objects.all().values('word'))
            free_words_count = free_saved_words.count()
            if free_words_count > 10 - cards_created_today_count:
                for word in free_saved_words[:10 - cards_created_today_count]:
                    fc = Flashcard.objects.create(
                        user=request.user, word=word)
            else:
                for word in free_saved_words:
                    Flashcard.objects.create(
                        user=request.user, word=word)
        # return 15 cards for the day
        reviewed_cards_today = \
            Review.objects.filter(
                date_added__date=now,
                card__in=Flashcard.objects.filter(
                    user=request.user))
        reviewed_cards_count = reviewed_cards_today.count()
        if reviewed_cards_count < 15:
            due_cards = \
                Flashcard.objects.filter(
                    user=request.user, due__lte=now + timedelta(days=1))
            if len(due_cards) > 15 - reviewed_cards_count:
                cards += list(due_cards[:15 - reviewed_cards_count])
            else:
                cards += list(due_cards)
        return JsonResponse({
            'cards': json.loads(serializers.serialize('json', cards))
        })

    def post(self, request):
        """Returns a list of newly created Review objects. Details can be found in the technical spec."""
        new_reviews = []
        now = datetime.now()
        data = json.loads(request.body)
        for card_id, answer in data['reviews']:
            card = Flashcard.objects.get(
                user=request.user, id=card_id)
            easy_reviews = \
                Review.objects.filter(
                    card=card,
                    answer__exact='E',
                    date_added__gte=now - timedelta(30))
            hard_reviews = \
                Review.objects.filter(
                    card=card,
                    answer__exact='H',
                    date_added__gte=now - timedelta(30))
            forgot_reviews = \
                Review.objects.filter(
                    card=card,
                    answer__exact='F',
                    date_added__gte=now - timedelta(30))
            recent_review_days = \
                    easy_reviews.count()\
                    + 0.5 * hard_reviews.count()\
                    - 0.5 * forgot_reviews.count()
            duration = 24 * 3600 * recent_review_days
            if answer == 'E':
                if duration >= 0:
                    card.due = \
                        now + timedelta(days=3) + timedelta(seconds=duration)
                else:
                    card.due = now
            elif answer == 'H':
                if duration >= 0:
                    card.due = \
                        now + timedelta(days=1) + timedelta(seconds=duration)
                else:
                    card.due = now
            elif answer == 'F':
                if duration >= 0:
                    card.due = \
                        now + timedelta(days=1)
                else:
                    card.due = now
            card.save()
            new_reviews.append(
                    Review.objects.create(
                        card=card, answer=answer
                    )
                )
        return JsonResponse({
            'reviews': json.loads(serializers.serialize('json', new_reviews)),
        })
