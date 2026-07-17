from django import forms


class MovieFilterForm(forms.Form):
    q = forms.CharField(max_length=100, required=False, label='Пошук')
    genre = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Усі жанри',
        label='Жанр',
    )
    hall = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Усі зали',
        label='Зал',
    )
    date = forms.DateField(
        required=False,
        label='Дата сеансу',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, *args, **kwargs):
        genres = kwargs.pop('genres')
        halls = kwargs.pop('halls')
        super().__init__(*args, **kwargs)
        self.fields['genre'].queryset = genres
        self.fields['hall'].queryset = halls
        for field in self.fields.values():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css_class)


class BookingForm(forms.Form):
    seats = forms.MultipleChoiceField(
        required=True,
        widget=forms.MultipleHiddenInput,
        error_messages={'required': 'Оберіть хоча б одне місце.'},
    )

    def __init__(self, *args, **kwargs):
        seat_choices = kwargs.pop('seat_choices')
        super().__init__(*args, **kwargs)
        self.fields['seats'].choices = seat_choices

    def clean_seats(self):
        seats = self.cleaned_data['seats']
        return list(dict.fromkeys(seats))
