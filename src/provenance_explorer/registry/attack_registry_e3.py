# from E3 ground truth file
#
# (start, end) of active attacker interaction only
# times ae UTC -4 and need to be converted to the actual timestamps like so
# t_start = date_string_to_ns_timestamp(
#     "2018-04-10 14:30:00", tz=timezone(timedelta(hours=-4))
# )

e3_cadets_host = {
    ("2018-04-06 11:20:00", "2018-04-06 12:10:00"): {
        "descrpt": "Nginx Backdoor w/ Drakon In-Memory (first attempt)",
        "report_sec": "3.1",
        "tactics": [
            "Initial Access", # Nginx exploit via malformed HTTP POST
            "Execution", # loaderDrakon, elevated vUgefal process, netrecon module
            "Persistence", # ATTEMPTED sshd injection (PID 809) failed
            "Privilege Escalation", # elevate /tmp/vUgefal -> root
            "Defense Evasion", # libdrakon staged at /var/log/devc (log-path masquerade); in-memory loader
            "Discovery", # nrinfo, ps, netrecon module
            "Command and Control", # loaderDrakon console, nrtcp to 61.167.39.128:80
        ],
    },

    ("2018-04-06 15:00:00", "2018-04-06 15:20:00"): {
        "descrpt": "Postfix relay used for phishing",
        "report_sec": "4.1",
        "tactics": [], # unclear whether this belongs in cadets attack timeline at all; 'infrastructure abuse'
    },

    ("2018-04-11 15:08:00", "2018-04-11 15:15:00"): {
        "descrpt": "Nginx Backdoor w/ Drakon In-Memory (second attempt, retry of injection)",
        "report_sec": "3.8",
        "tactics": [
            "Initial Access", # Nginx re-exploited with malformed HTTP POSD
            "Execution", # loaderDrakon in nginx memory
            "Persistence", # ATTEMPTED sshd PID 802 injection failed, caused kernel panic
            "Defense Evasion", # libdrakon staged as /tmp/grain, in-memory loader
            "Command and Control", # loaderDrakon shell
            # No Privilege Escalation in this window (no elevate before crash)
        ],
    },

    ("2018-04-12 14:00:00", "2018-04-12 14:38:00"): {
        "descrpt": "Nginx Backdoor w/ Drakon In-Memory + micro APT portscan",
        "report_sec": "3.13",
        "tactics": [
            "Initial Access", # Nginx re-exploited with malformed HTTP POST
            "Execution", # loaderDrakon, drakon XIM elevated to root, micro APT (sendmail)
            "Privilege Escalation", # elevate /tmp/XIM succeeded (multiple micro APT elevates FAILED)
            "Defense Evasion", # filenames mimicking system binaries (sendmail, tmux-1002, font, XIM)
            "Discovery", # micro APT portscan of 128.55.12.XX
            "Command and Control", # drakon XIM + micro APT sendmail
        ],
    },

    ("2018-04-13 09:04:00", "2018-04-13 09:16:00"): {
        "descrpt": "Nginx Backdoor w/ Drakon In-Memory (final injection attempt)",
        "report_sec": "3.14",
        "tactics": [
            "Initial Access", # same old Nginx
            "Execution", # loaderDrakon, pEja72mA drakon as root
            "Persistence", # ATTEMPTED sshd PID 20691 injection (memhelp.so/eraseme/done.so)
            "Privilege Escalation", # elevate /tmp/pEja72mA
            "Defense Evasion", # multiple renames of same .so (eWq10bVcx -> memhelp.so -> eraseme -> done.so), log-path-ish names
            "Discovery", # ps, whoami
            "Command and Control", # drakon pEja72mA connection
        ],
    },
}

e3_clearscope_host = {
    ("2018-04-06 15:02:00", "2018-04-06 15:17:00"): {
        "descrpt": "Phishing E-mail Link -> credential harvest (nasa.ng / foo1.com)",
        "report_sec": "4.2",
        "tactics": [
            "Initial Access", # phishing link delivered via email
            "Execution", # user clicks link, browser renders page (user-execution)
            "Credential Access", # credential-harvest form on www.nasa.ng
            "Collection", # credentials submitted
            "Exfiltration", # POST to www.foo1.com (208.75.117.2)
        ],
        # NOTE: pure phish, maybe ditch to not confuse with interesting attacks
    },

    ("2018-04-11 13:55:00", "2018-04-11 14:47:00"): {
        "descrpt": "Firefox Backdoor w/ Drakon In-Memory (mit.gov.jo)",
        "report_sec": "3.6",
        "tactics": [
            "Initial Access", # Firefox exploit via www.mit.gov.jo
            "Execution", # drakon in firefox memory; elevated shared_files drakon as root
            "Privilege Escalation", # elevate /data/.../shared_files
            "Defense Evasion", # in-memory loader; filename csb.tracee.27331.27355
            "Persistence", # inject into PID 424 (installd) failed
            "Discovery", # cat hosts
            "Exfiltration", # exfil over C2 channel; not collection, as this is not used downstream
            "Command and Control", # connections A1-A4
        ],
    },

    ("2018-04-12 15:19:00", "2018-04-12 15:30:00"): {
        "descrpt": "Continuation: re-use A4, further injection attempts (all failed)",
        "report_sec": "3.7",
        "tactics": [
            "Execution", # second drakon process elevated (shared_lib, A5)
            "Persistence", # sshd injection (PID 424 installd) failed twice
            "Privilege Escalation", # elevate shared_lib
            "Defense Evasion", # file names (libs, shared_lib, tmp18d17sn1); rm after use
            "Command and Control", # re-use of open A4 channel + new A5
        ],
    },
}

e3_fivedirections_host = {
    ("2018-04-09 13:19:00", "2018-04-09 15:42:00"): {
        "descrpt": "Phishing E-mail w/ Excel Macro (manual execution after auto-run failed)",
        "report_sec": "4.4",
        "tactics": [
            "Initial Access", # phishing email w/ BoviaBenefitsOE.xlsm
            "Execution", # user opened xlsm; macro auto-run FAILED, then manual powershell -encodedCommand
            "Defense Evasion", # base64-encoded powershell command; -ep bypass; downloadfile via WebClient
            "Discovery", # type hosts, type Document.rtf / MissleAlert.rtf / trains.rtf
            "Exfiltration", # type on document files
            "Command and Control", # powercat reverse shell to 208.75.117.6:80
        ],
    },

    ("2018-04-11 10:00:00", "2018-04-11 10:40:00"): {
        "descrpt": "Firefox Backdoor w/ Drakon In-Memory (www.cnpc.com.cn)",
        "report_sec": "3.4",
        "tactics": [
            "Initial Access", # Firefox exploit via cnpc.com.cn ad
            "Execution", # drakon in firefox memory; netrecon module
            "Defense Evasion", # in-memory loader
            "Discovery", # hostname, netrecon (nrtcp, nrudp)
            "Collection", # cat on Documents/* (trains, Missledefence, Covert.xlsx, etc.)
            "Exfiltration", # getfile over OC2
            "Command and Control", # OC2 + netrecon channels
        ],
    },

    ("2018-04-12 11:13:00", "2018-04-12 11:14:00"): {
        "descrpt": "Browser Extension w/ Drakon Dropper FAILED end-to-end",
        "report_sec": "3.10",
        "tactics": [
            "Initial Access", # browser extension load via www.allstate.com
            "Execution", # drakon execution from disk -> crashed, no callback
            "Defense Evasion", # dropper wrote to C:\Program Files\Mozilla Firefox\add-on\hJauWl01
        ],
    },
}

e3_theia_host = {
    ("2018-04-10 13:00:00", "2018-04-10 13:42:00"): {
        "descrpt": "Phishing E-mail Link -> credential harvest (nasa.ng / foo1.com)",
        "report_sec": "4.6",
        "tactics": [
            "Initial Access", # phishing link (impersonating Bob)
            "Execution", # user execution clicks link
            "Credential Access", # nasa.ng form
            "Exfiltration", # POST to foo1.com
        ],
        # NOTE: phishing only 
    },

    ("2018-04-10 13:41:00", "2018-04-10 14:56:00"): {
        "descrpt": "Firefox Backdoor w/ Drakon In-Memory (allstate.com then gatech.edu)",
        "report_sec": "3.3",
        "tactics": [
            "Initial Access", # Firefox exploit (allstate.com failed, gatech.edu succeeded)
            "Execution", # drakon in-memory; clean/profile elevated drakon
            "Privilege Escalation", # elevate /home/admin/profile
            "Defense Evasion", # libdrakon staged at /var/log/xdev; rm clean/profile after use
            "Discovery", # netrecon (nrtcp 7.149.198.40)
            "Command and Control", # multiple shells; L5 left open
        ],
    },

    ("2018-04-12 12:44:00", "2018-04-12 13:26:00"): {
        "descrpt": "Browser Extension w/ Drakon Dropper + Micro APT portscan",
        "report_sec": "3.11",
        "tactics": [
            "Initial Access", # browser extension via gatech.edu
            "Execution", # drakon dropper; micro APT (mail) elevated as root
            "Privilege Escalation", # elevate /var/log/mail
            "Persistence", # ATTEMPTED sshd PID 1226 injection (xdev/wdev/memtrace.so) all failed
            "Defense Evasion", # log-path masquerade (/var/log/xdev, /var/log/mail); rm after use; cp renames
            "Discovery", # whoami, ps, micro APT portscan
            "Command and Control", # gtcache drakon + micro APT C2
        ],
    },
}

e3_trace_host = {
    ("2018-04-10 09:46:00", "2018-04-10 11:09:00"): {
        "descrpt": "Firefox Backdoor w/ Drakon In-Memory (allstate.com)",
        "report_sec": "3.2",
        "tactics": [
            "Initial Access", # Firefox exploit via allstate.com ad
            "Execution", # drakon in-memory; cache drakon elevated as root
            "Privilege Escalation", # elevate /home/admin/cache
            "Defense Evasion", # libdrakon staged at /var/log/xtmp; in-memory loader
            "Command and Control", # OC2 shells; L3 left open (later lost on OC2 crash)
        ],
    },

    ("2018-04-10 12:28:00", "2018-04-10 12:35:00"): {
        "descrpt": "Phishing E-mail Link -> credential harvest (nasa.ng / foo1.com)",
        "report_sec": "4.5",
        "tactics": [
            "Initial Access", # mail
            "Execution", # user clicks link
            "Credential Access", # post form 
        ],
    },

    ("2018-04-12 13:36:00", "2018-04-12 13:37:00"): {
        "descrpt": "Browser Extension  FAILED (Firefox hung, no callback)",
        "report_sec": "3.12",
        "tactics": [
            "Initial Access", # browser extension exploit via allstate.com failed
        ],
    },

    ("2018-04-13 12:43:00", "2018-04-13 12:53:00"): {
        "descrpt": "Pine Backdoor w/ Drakon Dropper + Micro APT portscan (portscan returned nothing)",
        "report_sec": "3.15",
        "tactics": [
            "Initial Access", # pass-manager browser extension via allstate.com (title says Pine Backdoor ?? but events say allstate.com browser ext)
            "Execution", # ztmp drakon; micro APT execfile
            "Privilege Escalation", # ATTEMPTED elevate ztmp failed (elevate driver not re-installed post-reboot)
            "Defense Evasion", # drop to /tmp/ztmp, rm after
            "Discovery", # micro APT portscan (no open ports found)
            "Command and Control", # micro APT + netrecon2 channels
        ],
    },

    ("2018-04-13 13:50:00", "2018-04-13 14:28:00"): {
        "descrpt": "Phishing E-mail w/ Executable Attachment + Pine exploit + Micro APT",
        "report_sec": "4.9",
        "tactics": [
            "Initial Access", # phishing email w/ tcexec attachment; second email w/ micro apt
            "Execution", # user ran tcexec (failed, missing QT lib); micro apt ran via vulnerable Pine
            "Defense Evasion", # attachment-named-tcexec; pine auto-exec of attachment
            "Discovery", # micro APT portscan
            # "Collection", # tcexfil file written to /tmp (Pine-backdoor exfil staging)
            "Exfiltration", # tcexfil (staged for exfil per sec 4.9.1); likely exfild, but not reported 
            "Command and Control", # micro APT C2 (162.66.239.75)
        ],
    },
}

