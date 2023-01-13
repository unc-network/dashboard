from django import forms
from django.forms import ValidationError

DEPT_CHOICES = (
    ('ITS-Net-Deployment', 'Deployment'),
    ('ITS-Networking', 'Engineering'),
    ('ITS-Net-WIFI', 'Wireless'),
    ('IP-Services', 'IP Services'),
    ('SOMIT-Networking', 'SoM'),
)

CRITICAL_CHOICES = (
    ('Critical', 'Critical'),
    ('High', 'High'),
    ('Moderate', 'Moderate'),
    ('Low', 'Low'),
)


class IncidentForm(forms.Form):
    summary_events = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    trap_events = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    description = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': '3',
                'placeholder': 'Enter....'
            }
        )
    )
    assignment_group = forms.ChoiceField(
        choices=DEPT_CHOICES,
        widget=forms.RadioSelect
    )
    criticality = forms.ChoiceField(
        choices=CRITICAL_CHOICES,
        widget=forms.RadioSelect
    )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('summary_events') and not cleaned_data.get('trap_events'):
            raise ValidationError(
                {'summary_events': 'At least one summary or trap must be selected'})

class HibernateForm(forms.Form):
    TYPE_CHOICES = (
        ('Auto', 'Auto clear'),
        ('Time', 'Clear at time'),
        ('Manual', 'Never clear'),
    )
    device_ids = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    type = forms.ChoiceField(
        choices=TYPE_CHOICES,
        widget=forms.RadioSelect
    )
    clear_time = forms.DateTimeField(
        required=False,
        input_formats=['%m/%d/%Y %H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                'class': 'form-control datetimepicker-input',
                'data-target': '#reservationdatetime'
            }
        )
    )
    comment = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': '3',
                'placeholder': 'Enter....'
            }
        )
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('type','') == 'Time' and not cleaned_data.get('clear_time') :
            raise ValidationError(
                {'clear_time': 'A time is required'})
