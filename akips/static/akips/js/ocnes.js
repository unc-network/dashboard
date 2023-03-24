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
    var alert_toggle = $('#alert-toggle').prop('checked') // Boolean
    var alert_url = $('#alert-toggle').data('alert-url')

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
                } else if ( data.level == 'danger' ) {
                    // Use HTML5 audio for important alerts 
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

function enable_alert_toggle() {
    // Configure the user preference switch
    $(document).on('change', 'input.alert-toggle', function () {
        var url = $(this).data("url");
        if (this.checked) {
            console.log("alert checkbox on");
            $.get(url, { "alert_enabled": 'True' })
        } else {
            console.log("alert checkbox off")
            $.get(url, { "alert_enabled": 'False' })
        }
    });
}