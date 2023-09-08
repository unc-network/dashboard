use MIME::Base64 qw(encode_base64);

my $OCNES_URL = "https://ocnes.example.com/webhook/";
my $OCNES_TOKEN = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";

sub custom_post_status_to_dashboard
{  
    my ($arg_ref) = @_;
    # Parameters from alert
    my $kind = $arg_ref->{kind};
    my $tt       = $arg_ref->{tt};
    my $device   = $arg_ref->{device};
    my $child   = $arg_ref->{child};
    my $descr   = $arg_ref->{descr};
    my $attr   = $arg_ref->{attr};
    my $alias   = $arg_ref->{alias};
    my $state   = $arg_ref->{state};

    my %dashboard;
    $dashboard{url}          = $OCNES_URL;
    $dashboard{headers}      = ["Akips-Webhook-Token: $OCNES_TOKEN" ];
    $dashboard{method}       = "post";
    $dashboard{content_type} = "application/json";

    # Uncomment the following line to use proxy
    # $dashboard{proxy}      = "http://xxxx:3128";

    my $data = {
        "type"   => "Status",
        "kind"   => $kind,
        "tt"     => $tt,
        "device" => $device,
        "child"  => $child,
        "descr"  => $descr,
        "attr"   => $attr,
        "alias"  => $alias,
        "state"  => $state
    };
    $dashboard{data} = encode_json $data;

    http_result (\%dashboard);
}

sub custom_post_trap_to_dashboard
{
    my ($arg_ref) = @_;
    # Parameters from alert
    my $tt       = $arg_ref->{tt};
    my $device   = $arg_ref->{device};
    my $ipaddr   = $arg_ref->{ipaddr};
    my $trap_oid = $arg_ref->{trap_oid};
    my $uptime = $arg_ref->{uptime};
    my $oids      = $arg_ref->{oids};
        
    my %dashboard;
    $dashboard{url}          = $OCNES_URL;
    $dashboard{headers}      = ["Akips-Webhook-Token: $OCNES_TOKEN" ];
    $dashboard{method}       = "post";
    $dashboard{content_type} = "application/json";

    # Uncomment the following line to use proxy
    # $dashboard{proxy}      = "http://xxxx:3128";

    my $data = {
        "type"     => "Trap",
        "tt"       => $tt,
        "device"   => $device,
        "ipaddr"   => $ipaddr,
        "trap_oid" => $trap_oid,
        "uptime"   => $uptime,
        "oids"     => $oids 
    };
    $dashboard{data} = encode_json $data;

    http_result (\%dashboard);
}