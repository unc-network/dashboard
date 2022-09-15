from django import forms

DEPT_CHOICES = (
    ('Deployment','Deployment'),
    ('Engineering','Engineering'),
    ('Wireless','Wireless'),
    ('SoM','SoM'),
)

CRITICAL_CHOICES = (
    ('Normal','Normal'),
    ('Critical','Critical'),
)

class IncidentForm(forms.Form):
    summary_events = forms.JSONField() 
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
        widget=forms.RadioSelect(
            attrs={
                'class': 'custom-select', 
                }
            )
        )
    criticality = forms.ChoiceField(widget=forms.RadioSelect, choices = CRITICAL_CHOICES)
