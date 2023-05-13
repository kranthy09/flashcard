import json
from datetime import datetime, timedelta
from typing import Optional

from django.contrib.auth.models import User
from django.core import serializers
from django.db import transaction
from django.test import TestCase

from flashcards.models import SavedWord, Flashcard, Review
from flashcards.views import FlashcardView


class FlashcardViewTest(TestCase):
    def setUp(self) -> None:
        self.client = self.client_class()
        self.user = User.objects.create_user('testuser')
        self.user_words = SavedWord.objects.bulk_create(
            [SavedWord(user=self.user, word=f'word{i}', definition=f'def{i}')
             for i in range(30)]
        )
        self.client.force_login(self.user)

    def test_limited_new_words(self):
        target_card_count = 3
        Flashcard.objects.bulk_create(
            [Flashcard(user=self.user, word=word)
             for word in self.user_words[:-target_card_count]]
        )
        # Set the date added of all the cards to yesterday, so they don't influence the
        # card count today.
        yesterday = datetime.now() - timedelta(days=1)
        Flashcard.objects.all().update(date_added=yesterday, due=yesterday)

        cur_count = Flashcard.objects.filter(user=self.user).count()

        response = self.client.get('/flashcards/')
        self.assertEqual(response.status_code, 200)
        new_count = Flashcard.objects.filter(user=self.user).count()

        self.assertEqual(new_count - cur_count, target_card_count)
        response_cards = [
            x.object for x in
            serializers.deserialize('json', json.dumps(response.json()['cards']))
        ]

        self.assertTrue(all(response_cards[i].due <= response_cards[i+1].due
                            for i in range(len(response_cards) - 1)))
        self.assertEqual(len(response.json()['cards']), FlashcardView.MAX_TOTAL_CARDS)

    def test_limited_cards_today(self):
        target_card_count = 3
        Flashcard.objects.bulk_create(
            [Flashcard(user=self.user, word=word)
             for word in self.user_words[:FlashcardView.MAX_NEW_CARDS-target_card_count]]
        )

        cur_count = Flashcard.objects.filter(user=self.user).count()
        response = self.client.get('/flashcards/')
        self.assertEqual(response.status_code, 200)
        new_count = Flashcard.objects.filter(user=self.user).count()

        self.assertEqual(new_count - cur_count, target_card_count)
        response_cards = [
            x.object for x in
            serializers.deserialize('json', json.dumps(response.json()['cards']))
        ]

        self.assertTrue(all(card.date_added.date() == datetime.today().date()
                            for card in response_cards))
        self.assertTrue(all(response_cards[i].due <= response_cards[i+1].due
                            for i in range(len(response_cards) - 1)))
        self.assertEqual(len(response.json()['cards']), cur_count + target_card_count)

    def _make_cards_for_post(self, count: Optional[int] = None):
        if count is None:
            count = len(self.user_words)
        Flashcard.objects.bulk_create(
            [Flashcard(user=self.user, word=word) for word in self.user_words][:count]
        )
        two_months_ago = datetime.now() - timedelta(days=60)
        Flashcard.objects.all().update(date_added=two_months_ago,
                                       due=datetime.now() - timedelta(days=1))

    def _verify_post_response(self, response, target_cards, answers):
        self.assertEqual(response.status_code, 200)
        response_reviews = [
            x.object for x in
            serializers.deserialize('json', json.dumps(response.json()['reviews']))
        ]

        self.assertEqual(len(response_reviews), len(target_cards))
        self.assertTrue(all(review.answer == answer for review, answer in zip(response_reviews, answers)))
        self.assertTrue(all(review.card in target_cards for review in response_reviews))

        return response_reviews

    def test_post(self):
        self._make_cards_for_post()

        target_cards = Flashcard.objects.filter(user=self.user).order_by('due')[:3]

        response = self.client.post('/flashcards/', content_type='application/json',
                                    data=json.dumps({'reviews': [
                                        (card.id, Review.Answer.HARD.value)
                                        for card in target_cards
                                    ]}))

        self._verify_post_response(response, target_cards, [Review.Answer.HARD] * len(target_cards))
        # have to use card_id__in here, somehow the deserialized cards don't work right for querying card__in
        self.assertEqual(Review.objects.filter(card_id__in=[t.id for t in target_cards]).count(),
                         len(target_cards))

    def test_post_due_dates(self):
        self._make_cards_for_post()

        target_cards = Flashcard.objects.filter(user=self.user).order_by('due')[:5]
        recent_reviews_by_card_id = {
            target_cards[0].id: [
                Review(card=target_cards[0], answer=Review.Answer.HARD),
                Review(card=target_cards[0], answer=Review.Answer.EASY),
                Review(card=target_cards[0], answer=Review.Answer.FORGOT),
            ],
            target_cards[1].id: [],
            target_cards[2].id: [Review(card=target_cards[2], answer=Review.Answer.FORGOT)] * 4,
            target_cards[3].id: [
                Review(card=target_cards[3], answer=Review.Answer.EASY),
            ],
            target_cards[4].id: [Review(card=target_cards[4], answer=Review.Answer.EASY)] * 2,
        }

        for _, reviews in recent_reviews_by_card_id.items():
            Review.objects.bulk_create(reviews)

        with transaction.atomic():
            for review in Review.objects.all():
                review.date_added = datetime.now() - timedelta(days=1)
                review.save()
        answer_by_card_id = {
            target_cards[0].id: Review.Answer.HARD,
            target_cards[1].id: Review.Answer.EASY,
            target_cards[2].id: Review.Answer.HARD,
            target_cards[3].id: Review.Answer.FORGOT,
            target_cards[4].id: Review.Answer.FORGOT,
        }

        old_review_count = Review.objects.filter(card_id__in=[t.id for t in target_cards]).count()
        response = self.client.post('/flashcards/', content_type='application/json',
                                    data=json.dumps({'reviews': [
                                        (card.id, answer_by_card_id[card.id].value)
                                        for card in target_cards
                                    ]}))

        self._verify_post_response(response, target_cards, [
            answer_by_card_id[card.id] for card in target_cards
        ])
        new_review_count = Review.objects.filter(card_id__in=[t.id for t in target_cards]).count()
        self.assertEqual(new_review_count - old_review_count, len(target_cards))

        db_cards = Flashcard.objects.filter(user=self.user, id__in=[card.id for card in target_cards]).order_by('id')

        # computed like this when helper is available, helper is removed for assignment
        # from helpers import new_review_date
        # expected_offset_by_card_id = {
        #     card.id: (new_review_date(answer_by_card_id[card.id], recent_reviews_by_card_id[card.id])
        #               .replace(second=0, microsecond=0, tzinfo=None)
        #               - datetime.now().replace(second=0, microsecond=0, tzinfo=None)
        #               ).days
        #     for card in target_cards
        # }
        expected_offset_by_card_id = {1: 2, 2: 3, 3: 0, 4: 1, 5: 1}

        for card in db_cards:
            self.assertEqual((card.due.replace(second=0, microsecond=0, tzinfo=None)
                              - datetime.now().replace(second=0, microsecond=0, tzinfo=None)).days,
                             expected_offset_by_card_id[card.id])

    def test_review_reduces_get_cards(self):
        Flashcard.objects.bulk_create(
            [Flashcard(user=self.user, word=word)
             for word in self.user_words][:FlashcardView.MAX_TOTAL_CARDS + 5]
        )

        response = self.client.get('/flashcards/')
        self.assertEqual(response.status_code, 200)
        first_response_cards = [
            x.object for x in
            serializers.deserialize('json', json.dumps(response.json()['cards']))
        ]
        first_response_len = len(first_response_cards)
        self.assertEqual(first_response_len, FlashcardView.MAX_TOTAL_CARDS)

        review_count = 5
        response = self.client.post('/flashcards/', content_type='application/json',
                                    data=json.dumps({'reviews': [
                                        (card.id, Review.Answer.EASY.value)
                                        for card in first_response_cards[:review_count]
                                    ]}))

        self._verify_post_response(response, first_response_cards[:review_count],
                                   [Review.Answer.EASY] * review_count)

        response = self.client.get('/flashcards/')
        self.assertEqual(response.status_code, 200)
        second_response_cards = [
            x.object for x in
            serializers.deserialize('json', json.dumps(response.json()['cards']))
        ]
        self.assertEqual(len(second_response_cards), first_response_len - review_count)



