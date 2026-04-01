// Basic functions for the OCNES site.

const OCNES_VOICE_SETTINGS_KEY = 'ocnes_voice';

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

// Voice settings are stored in localStorage, with cookie fallback for migration.
function getVoiceSettingsRaw() {
    try {
        var local = window.localStorage.getItem(OCNES_VOICE_SETTINGS_KEY);
        if (local) {
            return local;
        }
    } catch (e) {
        // Ignore storage access errors
    }

    var legacyCookie = getCookie(OCNES_VOICE_SETTINGS_KEY);
    if (legacyCookie) {
        try {
            window.localStorage.setItem(OCNES_VOICE_SETTINGS_KEY, legacyCookie);
        } catch (e) {
            // Ignore storage access errors
        }
        deleteCookie(OCNES_VOICE_SETTINGS_KEY);
        return legacyCookie;
    }

    return "";
}

function getVoiceSettings() {
    var speech_json = getVoiceSettingsRaw();
    if (!speech_json) {
        return null;
    }
    try {
        return JSON.parse(speech_json);
    } catch (e) {
        return null;
    }
}

function setVoiceSettings(speech) {
    try {
        window.localStorage.setItem(OCNES_VOICE_SETTINGS_KEY, JSON.stringify(speech));
    } catch (e) {
        // Ignore storage access errors
    }
}

function clearVoiceSettings() {
    try {
        window.localStorage.removeItem(OCNES_VOICE_SETTINGS_KEY);
    } catch (e) {
        // Ignore storage access errors
    }
    deleteCookie(OCNES_VOICE_SETTINGS_KEY);
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
    var toggle = $('#alert-toggle');
    var alert_url = toggle.data('alert-url');

    if (!alert_url) {
        return;
    }

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
                    var speech = getVoiceSettings();
                    if (speech) {
                        // Get user preferences from local storage
                        console.log("Using saved voice setting for voice " + speech.voice + " with rate " + speech.rate + " and pitch " + speech.pitch);
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

function set_alert_toggle_state(enabled) {
    var toggle = $('#alert-toggle');
    if (!toggle.length) {
        return;
    }

    toggle.data('enabled', !!enabled);
    toggle.attr('aria-pressed', !!enabled ? 'true' : 'false');
    toggle.attr('title', !!enabled ? 'Notifications: On' : 'Notifications: Off');

    var icon = $('#alert-toggle-icon');
    if (icon.length) {
        icon.removeClass('fa-volume-up fa-volume-mute');
        icon.addClass(enabled ? 'fa-volume-up' : 'fa-volume-mute');
    }
}

function get_alert_toggle_state() {
    var toggle = $('#alert-toggle');
    if (!toggle.length) {
        return true;
    }
    var enabled = toggle.data('enabled');
    return typeof enabled === 'undefined' ? true : !!enabled;
}

function enable_alert_toggle() {
    // Initialize from user profile API so templates do not need to query profile directly.
    var toggle = $('#alert-toggle');
    var url = toggle.data('url');
    if (toggle.length && url) {
        $.get(url, function (data) {
            if (typeof data.alert_enabled !== 'undefined') {
                set_alert_toggle_state(!!data.alert_enabled);
            }
        });
    }

    // Configure the user preference icon toggle.
    $(document).off('click.alertToggle', '#alert-toggle').on('click.alertToggle', '#alert-toggle', function (e) {
        e.preventDefault();
        var current = get_alert_toggle_state();
        var next = !current;
        set_alert_toggle_state(next);

        var endpoint = $(this).data('url');
        if (endpoint) {
            $.get(endpoint, { "alert_enabled": next ? 'True' : 'False' });
        }
    });
}