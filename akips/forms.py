from django import forms
from django.forms import ValidationError
from django.contrib.auth.forms import AuthenticationForm

import re

from .models import TDXConfiguration, InventoryConfiguration, AKIPSConfiguration

class LoginForm(AuthenticationForm):
    ''' A form for logging a user in '''
    remember_me = forms.BooleanField(required=False)  # and add the remember_me field

## Form specific list of options
DEPT_CHOICES = (
    ('ITS-Networking-Deployment', 'Deployment'),
    ('ITS-Networking', 'Engineering'),
    ('ITS-Networking-WIFI', 'Wireless'),
    ('ITS-Networking-AdvancedServices', 'Advanced Services'),
    ('SOMIT-Networking', 'SoM Networking'),
)

CRITICAL_CHOICES = (
    ('emergency', 'Emergency'),
    ('high', 'High'),
    ('medium', 'Medium'),
    ('low', 'Low'),
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
    number = forms.IntegerField(
        label='Incident Number',
        help_text='TDX Ticket Number',
        min_value=1000,
        widget = forms.TextInput(attrs={'class':'form-control col-auto'}),
        required=False
    )
    # number = forms.CharField(
    #     label='Incident Number',
    #     help_text='TDX Ticket Number',
    #     max_length=16,
    #     widget = forms.TextInput(attrs={'class':'form-control col-auto'}),
    #     required=False
    # )

    # def clean_number(self):
    #     number = self.cleaned_data['number']
    #     if number and not re.match('^\d{5,8}', number, re.IGNORECASE):
    #         raise ValidationError("Incident numbers start with INC and include 7 digits")            
    #     return number

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


class AppSnapshotImportForm(forms.Form):
    clear_existing_data = forms.BooleanField(
        label='Clear existing app data before import',
        required=False,
        initial=True,
        help_text='Recommended when restoring from another environment to avoid duplicate key conflicts.',
        widget=forms.CheckboxInput(attrs={'class': 'custom-control-input'})
    )

    snapshot_file = forms.FileField(
        label='Snapshot file',
        help_text='Upload a JSON fixture exported from this app.',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control-file'})
    )

    def clean_snapshot_file(self):
        snapshot_file = self.cleaned_data['snapshot_file']
        name = snapshot_file.name.lower()
        if not (name.endswith('.json') or name.endswith('.json.gz')):
            raise ValidationError('Snapshot file must end with .json or .json.gz')
        return snapshot_file


class TDXSettingsForm(forms.ModelForm):
    class Meta:
        model = TDXConfiguration
        fields = ['enabled', 'api_url', 'flow_url', 'username', 'password', 'apikey']
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': 'custom-control-input'}),
            'api_url': forms.URLInput(attrs={'class': 'form-control'}),
            'flow_url': forms.URLInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control'}, render_value=True),
            'apikey': forms.PasswordInput(attrs={'class': 'form-control'}, render_value=True),
        }
        labels = {
            'enabled': 'Enable TDX updates',
            'api_url': 'API URL',
            'flow_url': 'Flow URL',
            'apikey': 'API key',
        }


class InventorySettingsForm(forms.ModelForm):
    class Meta:
        model = InventoryConfiguration
        fields = ['enabled', 'inventory_url', 'inventory_token']
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': 'custom-control-input'}),
            'inventory_url': forms.URLInput(attrs={'class': 'form-control'}),
            'inventory_token': forms.PasswordInput(attrs={'class': 'form-control'}, render_value=True),
        }
        labels = {
            'enabled': 'Enable inventory feed',
            'inventory_url': 'Inventory URL',
            'inventory_token': 'Inventory token',
        }


class AKIPSSettingsForm(forms.ModelForm):
    class Meta:
        model = AKIPSConfiguration
        fields = ['enabled', 'server', 'username', 'password', 'verify_ssl']
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': 'custom-control-input'}),
            'server': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'akips.example.com'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control'}, render_value=True),
            'verify_ssl': forms.CheckboxInput(attrs={'class': 'custom-control-input'}),
        }
        labels = {
            'enabled': 'Enable AKIPS',
            'server': 'AKIPS Server',
            'username': 'Username',
            'password': 'Password',
            'verify_ssl': 'Verify SSL Certificate',
        }