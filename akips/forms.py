from django import forms
from django.forms import ValidationError
from django.contrib.auth.forms import AuthenticationForm

import re

class LoginForm(AuthenticationForm):
    ''' A form for logging a user in '''
    remember_me = forms.BooleanField(required=False)  # and add the remember_me field

## Form specific list of options
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
        help_text='Please enter any comments about this event below.',
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': '3',
                'placeholder': 'Enter....'
            }
        ),
        required=False
    )
    assignment_group = forms.ChoiceField(
        choices=DEPT_CHOICES,
        widget=forms.RadioSelect,
        required=False
    )
    criticality = forms.ChoiceField(
        choices=CRITICAL_CHOICES,
        widget=forms.RadioSelect,
        required=False
    )
    number = forms.CharField(
        label='Incident Number',
        help_text='i.e. INC000001',
        max_length=16,
        widget = forms.TextInput(attrs={'class':'form-control col-auto'}),
        required=False
    )

    def clean_number(self):
        number = self.cleaned_data['number']
        if number and not re.match('^INC\d{7}', number, re.IGNORECASE):
            raise ValidationError("Incident numbers start with INC and include 7 digits")            
        return number

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('summary_events') and not cleaned_data.get('trap_events'):
            raise ValidationError(
                {'summary_events': 'At least one summary or trap must be selected'})
        if not cleaned_data.get('number'):
            if not cleaned_data.get('description'):
                raise ValidationError({'description': 'Description is required'})
            if not cleaned_data.get('assignment_group'):
                raise ValidationError({'assignment_group': 'Assignment group is required'})
            if not cleaned_data.get('criticality'):
                raise ValidationError({'criticality': 'Criticality is required'})


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

class PreferencesForm(forms.Form):
    alert_enabled = forms.BooleanField(
        label='Enabled',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'custom-control-input'})
    )
    voice_enabled = forms.BooleanField(
        label='Use Voice',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'custom-control-input'})
    )
    # voice_default = forms.CharField()
    # voice_rate = forms.FloatField(
    #     min_value=0.5,
    #     max_value=2,
    #     widget=forms.NumberInput(attrs={'step': "0.1"})
    # )
    # voice_pitch = forms.FloatField(
    #     min_value=0.5,
    #     max_value=2,
    #     widget=forms.NumberInput(attrs={'step': "0.1"})
    # )