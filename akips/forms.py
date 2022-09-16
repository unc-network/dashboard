from django import forms

DEPT_CHOICES = (
    ('ITS-Net-Deployment','Deployment'),
    ('ITS-Networking','Engineering'),
    ('ITS-Net-WIFI','Wireless'),
    ('IP-Services','IP Services'),
    ('SoM','SoM'),
)

CRITICAL_CHOICES = (
    ('Critical','Critical'),
    ('High','High'),
    ('Moderate','Moderate'),
    ('Low','Low'),
)

class IncidentForm(forms.Form):
    summary_events = forms.CharField(
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
        choices = DEPT_CHOICES,
        widget=forms.RadioSelect
    )
    criticality = forms.ChoiceField(
        choices = CRITICAL_CHOICES,
        widget=forms.RadioSelect
    )
