// Basic functions for the OCNES site.

function refresh_alerts() {
    // Periodically check for user alerts.
    var refresh_seconds = 30000;

    alert_user();
    var intervalId = window.setInterval(function () {
        alert_user();
    }, refresh_seconds);
}

function alert_user() {
    // Poll for alerts and notify the user if needed.
    var alert_toggle = $('#voice-alert-toggle').prop('checked') // Boolean
    var alert_url = $('#voice-alert-toggle').data('alert-url')

    // console.log("Alerting user if necessary.");

    $.get( alert_url, function( data ) {
        var long_msg = data.messages.join(' ');
        if ( long_msg ) {
            // Audible alert if enabled
            if ( data.alert_enabled ) {
                const utterThis = new SpeechSynthesisUtterance(long_msg);
                if ( data.voice_enabled ) {
                    // Use Voice Synth
                    speechSynthesis.speak(utterThis);
                } else {
                    // Use HTML5 audio 
                    document.getElementById('audiotag1').play();
                }
            }
            // Display the popup alert even if alert is disabled
            $(document).Toasts('create', {
                class: 'bg-' + data.level,
                title: 'OCNES Notification',
                body: long_msg,
                autohide: true,
                delay: 30000
            });

        }
    })
}