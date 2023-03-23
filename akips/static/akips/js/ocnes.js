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
        if ( data.alert_enabled ) {
            data.messages.forEach(function (item) {
                var msg = new SpeechSynthesisUtterance(item);
                if ( data.voice_enabled ) {
                    speechSynthesis.speak(msg);
                } else {
                    document.getElementById('audiotag1').play();
                    // $('#audiotag1')[0].play();
                }
            })
        }
    })
}