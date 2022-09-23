from django import forms
from django.forms import ValidationError

DEPT_CHOICES = (
    ('ITS-Net-Deployment', 'Deployment'),
    ('ITS-Networking', 'Engineering'),
    ('ITS-Net-WIFI', 'Wireless'),
    ('IP-Services', 'IP Services'),
    ('SoM', 'SoM'),
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
