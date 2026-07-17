from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from cinema.models import Hall, Movie, Session

from .models import UserProfile


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Імʼя користувача')
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Email')
    full_name = forms.CharField(required=True, label='Повне імʼя')
    phone_number = forms.CharField(required=False, label='Телефон')
    birth_date = forms.DateField(
        required=False,
        label='Дата народження',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone_number', 'birth_date', 'password1', 'password2')
        labels = {
            'username': 'Імʼя користувача',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            profile = user.profile
            profile.full_name = self.cleaned_data['full_name']
            profile.phone_number = self.cleaned_data['phone_number']
            profile.birth_date = self.cleaned_data['birth_date']
            profile.save()
        return user


class ProfileForm(forms.ModelForm):
    email = forms.EmailField(required=True, label='Email')

    class Meta:
        model = UserProfile
        fields = ('full_name', 'phone_number', 'birth_date')
        labels = {
            'full_name': 'Повне імʼя',
            'phone_number': 'Телефон',
            'birth_date': 'Дата народження',
        }
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['email'].initial = user.email
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.email = self.cleaned_data['email']
        if commit:
            self.user.save(update_fields=['email'])
            profile.save()
        return profile


class StaffSessionForm(forms.ModelForm):
    show_date = forms.DateField(
        label='Дата',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    show_time = forms.TimeField(
        label='Час',
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )

    class Meta:
        model = Session
        fields = ('movie', 'hall', 'format_name', 'price', 'is_active')
        labels = {
            'movie': 'Фільм',
            'hall': 'Зал',
            'format_name': 'Формат',
            'price': 'Ціна',
            'is_active': 'Активний',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['movie'].queryset = Movie.objects.filter(is_active=True).order_by('title')
        self.fields['hall'].queryset = Hall.objects.order_by('name')
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            else:
                field.widget.attrs.setdefault('class', 'form-control')

    def save(self, commit=True):
        instance = super().save(commit=False)
        start_at = timezone.datetime.combine(
            self.cleaned_data['show_date'],
            self.cleaned_data['show_time'],
        )
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
        instance.start_at = start_at
        if commit:
            instance.save()
        return instance
