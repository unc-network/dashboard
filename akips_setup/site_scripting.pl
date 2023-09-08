use MIME::Base64 qw(encode_base64);

my $OCNES_URL = "https://ocnes.example.com/webhook/";
my $OCNES_TOKEN = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";

sub custom_post_status_to_dashboard
{  
    my ($arg_ref) = @_;

    my %dashboard;
    $dashboard{url}          = $OCNES_URL;
    $dashboard{headers}      = ["Akips-Webhook-Token: $OCNES_TOKEN" ];
    $dashboard{method}       = "post";
    $dashboard{content_type} = "application/json";

    my $data = {
        "type"   => "Status",
        "kind"   => $arg_ref->{kind},
        "tt"     => $arg_ref->{tt},
        "device" => $arg_ref->{device},
        "child"  => $arg_ref->{child},
        "descr"  => $arg_ref->{descr},
        "attr"   => $arg_ref->{attr},
        "alias"  => $arg_ref->{alias},
        "state"  => $arg_ref->{state}
    };
    $dashboard{data} = encode_json $data;

    http_result (\%dashboard);
}

sub custom_post_trap_to_dashboard
{
    my ($arg_ref) = @_;
        
    my %dashboard;
    $dashboard{url}          = $OCNES_URL;
    $dashboard{headers}      = ["Akips-Webhook-Token: $OCNES_TOKEN" ];
    $dashboard{method}       = "post";
    $dashboard{content_type} = "application/json";

    my $data = {
        "type"     => "Trap",
        "kind"     => $arg_ref->{kind},
        "tt"       => $arg_ref->{tt},
        "device"   => $arg_ref->{device},
        "ipaddr"   => $arg_ref->{ipaddr},
        "trap_oid" => $arg_ref->{trap_oid},
        "uptime"   => $arg_ref->{uptime},
        "oids"     => $arg_ref->{oids}
    };
    $dashboard{data} = encode_json $data;

    http_result (\%dashboard);
}