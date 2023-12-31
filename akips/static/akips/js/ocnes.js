// Basic functions for the OCNES site.

// Get the token to support AJAX POST
// function getCookie(name) {
//     var cookieValue = null;
//     if (document.cookie && document.cookie !== '') {
//         var cookies = document.cookie.split(';');
//         for (var i = 0; i < cookies.length; i++) {
//             var cookie = jQuery.trim(cookies[i]);
//             // Does this cookie string begin with the name we want?
//             if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                 cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                 break;
//             }
//         }
//     }
//     return cookieValue;
// }

// Get a cookie value
function getCookie(cname) {
    let name = cname + "=";
    let ca = document.cookie.split(';');
    for(let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

// Set a cookie value
function setCookie(cname, cvalue, exdays) {
    const d = new Date();
    d.setTime(d.getTime() + (exdays * 24 * 60 * 60 * 1000));
    let expires = "expires="+d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}

// Delete a cookie value
function deleteCookie(cname) {
    const d = new Date();
    d.setTime(d.getTime() - (1 * 24 * 60 * 60 * 1000));
    let expires = "expires="+d.toUTCString();
    document.cookie = cname + "= ;" + expires + ";path=/";
}

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

    // Handle rate, pitch, voice inputs
    const synth = window.speechSynthesis;

    // Voice options are async so some extra work is needed to set correctly
    let voices = [];
    function populateVoiceOptions() {
        voices = synth.getVoices();
    }
    populateVoiceOptions();
    if (synth.onvoiceschanged !== undefined) {
        synth.onvoiceschanged = populateVoiceOptions;
    }

    $.get( alert_url, function( data ) {
        var long_msg = data.messages.join(' ');
        if ( long_msg ) {
            // Audible alert if enabled
            if ( data.alert_enabled ) {
                if ( data.voice_enabled ) {
                    var msg = new SpeechSynthesisUtterance(long_msg);
                    // console.log("total voices " + voices.length);
                    var speech_json = getCookie('ocnes_voice');
                    if (speech_json) {
                        // Get user preferences from cookie
                        var speech = JSON.parse(speech_json);
                        console.log("Using cookie setting for voice " + speech.voice + " with rate " + speech.rate + " and pitch " + speech.pitch);
                        msg.rate = speech.rate;
                        msg.pitch = speech.pitch;
                        msg.voice = voices.filter(function(voice) { return voice.name == speech.voice; })[0];
                    }
                    // Use Voice Synth
                    synth.speak(msg);
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