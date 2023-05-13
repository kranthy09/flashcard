from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


# Create your models here.


class SavedWord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    word = models.CharField(max_length=50)
    definition = models.CharField(max_length=250)
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.word


class Flashcard(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    word = models.ForeignKey(SavedWord, on_delete=models.CASCADE)
    date_added = models.DateTimeField(auto_now_add=True)
    due = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'word'], name='unique_flashcard')
        ]
    
    def __str__(self) -> str:
        return "{} || {}".format(self.user, self.word)


class Review(models.Model):
    class Answer(models.TextChoices):
        EASY = 'E', _('Easy')
        HARD = 'H', _('Hard')
        FORGOT = 'F', _('Forgot')

    card = models.ForeignKey(Flashcard, on_delete=models.CASCADE)
    answer = models.CharField(max_length=1, choices=Answer.choices)
    date_added = models.DateTimeField(auto_now_add=True, db_index=True)

    @property
    def recent_review_days(self) -> float:
        return {
            Review.Answer.EASY: 1,
            Review.Answer.HARD: 0.5,
            Review.Answer.FORGOT: -0.5,
        }[self.Answer(self.answer)]