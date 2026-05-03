# from E5 ground truth file
#
# (start, end) of active attacker interaction only
# times ae UTC -4 and need to be converted to the actual timestamps like so
# t_start = date_string_to_ns_timestamp(
#     "2018-04-10 14:30:00", tz=timezone(timedelta(hours=-4))
# )

# ta1-cadets-1: 128.55.12.51
# // ta1-cadets-3: 128.55.12.106 only used for out-of-hours testing on 05-15; has uuid: CB02303B-654E-11E9-A80C-6C2B597E484C
e5_cadets_1 = {
    ("2019-05-10 10:44:00", "2019-05-10 10:49:00"): {
        "descrpt": "SSH login with stolen creds (see Nmap campaign §5.2); /home/admin/passwd exfil via SCP",
        "report_sec": "5.2",
        "tactics": [
            "Initial Access", # Valid Accounts SSH login on ta1-cadets-1 after nmap sweep
            # "Collection", # passwd file from admin
            "Discovery",# scp passwd -> ta51-pivot-1 (128.55.12.149)
        ],
        "labels": {
        },
        "host_uuid":"A3702F4C-5A0C-11E9-B8B9-D4AE52C1DBD3"
    },
    ("2019-05-10 13:44:00", "2019-05-10 13:46:00"): {
        "descrpt": "pivot out to THEIA-1",
        "report_sec": "5.2",
        "tactics": [
            "Lateral Movement", # ssh admin@128.55.12.110 from inside cadets-1
        ],
        "labels": {
        },
        "host_uuid":"A3702F4C-5A0C-11E9-B8B9-D4AE52C1DBD3"
    },
    ("2019-05-16 09:33:00", "2019-05-16 10:11:00"): {
        "descrpt": "Nginx Drakon APT attempt; exploit traffic to cadets-1 failed at 09:33 but an F1 callback at 09:59 self-reports as ta1-cadets-1",
        "report_sec": "9.3",
        "tactics": [
            "Initial Access", # malformed HTTP POST to 128.55.12.51:80 at 09:33 (Access denied)
            "Execution", # loaderDrakon in-memory (attributed to cadets-1 per callback hostname)
            "Defense Evasion", # in-memory, no disk artifact
            "Command and Control", # F1 to 4.21.51.250:80
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Nginx_Drakon_APT.csv"],
        },
        "host_uuid":"A3702F4C-5A0C-11E9-B8B9-D4AE52C1DBD3"
    },
    ("2019-05-17 10:16:00", "2019-05-17 10:19:00"): {
        "descrpt": "Nginx Drakon APT initial tries; C2 callbacks landed on wrong listener port (rediscovered at 13:30)",
        "report_sec": "10.4",
        "tactics": [
            "Initial Access", # malformed HTTP POST to 128.55.12.51:80
            "Execution", # loaderDrakon loaded in nginx memory (succeeded; callbacks F1/F2 on port 8888)
            "Defense Evasion", # in-memory
            "Command and Control", # drakon called home but to 128.55.12.167:8888
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Nginx_Drakon_APT_17.csv"],
        },
        "host_uuid":"A3702F4C-5A0C-11E9-B8B9-D4AE52C1DBD3"
    },
    ("2019-05-17 10:47:00", "2019-05-17 11:31:00"): {
        "descrpt": "Nginx Drakon APT re-run via ta51-pivot-2 OC2; /etc/passwd collection",
        "report_sec": "10.4",
        "tactics": [
            "Initial Access", # HTTP POST to 128.55.12.51:80
            "Execution", # loaderDrakon in-memory
            "Defense Evasion", # in-memory loader
            "Discovery", # cat /etc/passwd (account enum); cat /etc/shadow attempted failed (no root)
            "Command and Control", # F2 (src 128.55.12.51) -> 128.55.12.233:80
        ],
        # NOTE: subheader 10.4.3.4 is mis-labeled ta1-cadets-2 in the report
        "labels": {
            "pidsmaker": ["pidsmaker/node_Nginx_Drakon_APT_17.csv"],
        },
        "host_uuid":"A3702F4C-5A0C-11E9-B8B9-D4AE52C1DBD3"
    },
    ("2019-05-17 13:30:00", "2019-05-17 14:10:00"): {
        "descrpt": "Re-attached to the C2 sessions from 10:17/10:19 (port 8888); whoami/hostname, then quit",
        "report_sec": "10.4.4",
        "tactics": [
            "Command and Control", # reconnected to F1/F2 on port 8888
            # "Discovery", # whoami, hostname
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Nginx_Drakon_APT_17.csv"],
        },
        "host_uuid":"A3702F4C-5A0C-11E9-B8B9-D4AE52C1DBD3"
    },
}

# ta1-cadets-2: 128.55.12.75
e5_cadets_2 = {
    ("2019-05-16 09:32:00", "2019-05-16 09:37:00"): {
        "descrpt": "Nginx backdoor exploit POST sent three times to 128.55.12.75:80; loaderDrakon shellcode served at 09:35 and 09:36",
        "report_sec": "9.3",
        "tactics": [
            "Initial Access", # malformed HTTP POST to cadets-2 (09:32 failed, 09:34 + 09:36 retries)
            "Execution", # loaderDrakon shellcode written/served (251543 bytes served twice)
            "Defense Evasion", # in-memory loader
            "Command and Control", # shellcode successfully staged for actual C2 capability
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Nginx_Drakon_APT.csv"],
        },
        "host_uuid":"3A541941-5B04-11E9-B2DB-D4AE52C1DBD3"
    },
    ("2019-05-17 10:25:00", "2019-05-17 10:47:00"): {
        "descrpt": "Nginx Drakon APT; /etc/passwd exfil from cadets-2",
        "report_sec": "10.4 (F1)",
        "tactics": [
            "Initial Access", # malformed HTTP POST to 128.55.12.75:80 at 10:25
            "Execution", # loaderDrakon in-memory
            "Defense Evasion", # in-memory
            "Discovery", # whoami, hostname, pwd, getpid (ls failed non-root); passwd contents
            # "Credential Access", # cat /etc/passwd; cat shadow attempt failed
            # "Collection", # passwd contents
            # "Exfiltration", # passwd returned via C2
            "Command and Control", # F1 (src 128.55.12.75) -> 128.55.12.233:80 via ta51-pivot-2
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Nginx_Drakon_APT_17.csv"],
        },
        "host_uuid":"3A541941-5B04-11E9-B2DB-D4AE52C1DBD3"
    },
}

# likely (?)
# clearscope_1 = ta1-clearscope-translate @ 128.55.12.54  (production phone)
e5_clearscope_1 = {
    ("2019-05-14 16:09:00", "2019-05-14 17:10:00"): {
        "descrpt": "Barephone Micro APT FAILED (APK install hung >1hr)",
        "report_sec": "7.5",
        "tactics": [
            "Initial Access",   # ATTEMPTED only;  scp + adb install of instrumented Barephone APK
        ],
        "labels": {},
        "host_uuid":"860178F8-0FE9-66CC-8EE2-F6BBD1A59DAB"
    },
    ("2019-05-17 14:27:00", "2019-05-17 14:33:00"): {
        "descrpt": "MyApp/AppStarter Micro APT prep BinFmt-Elevate driver loaded, C2 FAILED",
        "report_sec": "10.9 (clearscope_1 portion)",
        "tactics": [
            "Initial Access", # ssh admin@.54 with stolen creds, adb push .ko modules
            "Execution", # insmod a64.ko (BinFmt-Elevate driver)
            "Privilege Escalation", # BinFmt-Elevate capability now loaded; driver grants root-on-trigger
            "Defense Evasion", # .ko files masqueraded as msm_g711tlaw.ko
        ],
        # AMBIGUITY: section §10.9 target table lists ONLY .114
        # But the event log at 14:29-14:33 shows explicit ssh to admin@128.55.12.54, showing driver setup happened on both
        "labels": {
            "pidsmaker": [
                "pidsmaker/node_clearscope_e5_appstarter_0515.csv",
            ],
        },
        "host_uuid":"860178F8-0FE9-66CC-8EE2-F6BBD1A59DAB"
    },

    ("2019-05-17 16:20:00", "2019-05-17 16:27:00"): {
        "descrpt": "Tester Micro APT + BinFmt-Elevate + DB exfil",
        "report_sec": "10.12",
        "tactics": [
            "Initial Access", # ssh admin@.54 (stolen creds, continuation)
            "Execution", # adb push tester ./tester in /data/local/tmp
            "Privilege Escalation", # elevate2 via BinFmt-Elevate uid 0 (after re-running as shell user)
            "Defense Evasion", # binary named "tester"; driver filename msm_g711tlaw.ko
            "Discovery", # whoami
            "Credential Access", # getfile of EmailProvider.db
            "Collection", # getfile of dialer.db, calendar.db, EmailProvider.db
            "Command and Control", # Micro APT C2 to ta1-pivot-2 (128.55.12.233) internal pivot
            "Exfiltration", # file contents streamed back over C2; MD5s logged at collector
        ],
        "labels": {
            "pidsmaker": [
                "pidsmaker/node_clearscope_e5_tester_0517.csv",
            ],
        },
        "host_uuid":"860178F8-0FE9-66CC-8EE2-F6BBD1A59DAB"
    },

    ("2019-05-15 15:39:00", "2019-05-15 16:18:00"): {
        "descrpt": "Appstarter APK Micro APT BinFmt-Elevate PII exfil + screenshot",
        "report_sec": "8.7",
        # !! full attck chain, highest-value clearscope attack of E5 !!
        "tactics": [
            "Initial Access", # scp + adb install of appstarter-instr.apk
            "Execution", # Appstarter launches Micro APT shared object in-process
            "Privilege Escalation", # elevate via /dev/msm_g711tlaw
            "Defense Evasion", # driver name mimics legit module
            "Discovery", # whoami, pwd, aptinfo (os/uname fingerprint)
            "Credential Access", # exfil of mmssms.db (SMS + contacts)
            "Collection", # calllog.db, calendar.db, mmssms.db exfil'd; screenshot captured post-elevate
            "Command and Control", # Micro APT C2 to external 77.138.117.150:80
            "Exfiltration", # db files over C2; and screenshot.png
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_clearscope_e5_appstarter_0515.csv"],
        },
        "host_uuid":"860178F8-0FE9-66CC-8EE2-F6BBD1A59DAB"
    },
}

# clearscope_2 = ta1-clearscope-translate-test is 128.55.12.114 (test phone)
e5_clearscope_2 = {
    ("2019-05-15 14:35:00", "2019-05-15 14:42:00"): {
        "descrpt": "Barephone Micro APT ch64 app crashed, no C2",
        "report_sec": "8.5",
        "substantive": False,# minor; APK ran but crashed before callback
        "tactics": [
            # "Initial Access", # (artificial) adb install -r barephone-instr.apk (after uninstall)
            "Execution", # barephone app launched via ADB remote control
            # nothing esle since app crashed at 14:42 before callback to 77.138.117.150:80.
        ],
        "labels": {
        },
        "host_uuid":"54FF20FC-635E-6455-F04F-EA4FA27EBC1E"
    },

    ("2019-05-17 11:50:00", "2019-05-17 11:58:00"): {
        "descrpt": "Firefox Drakon APT (www.nintendo.com exploit)",
        "report_sec": "10.5",
        "tactics": [
            "Initial Access", # browse to malicious www.nintendo.com, Firefox exploit
            "Execution", # Drakon APT loaded in Firefox memory
            "Defense Evasion", # in-memory loader, no disk artifact
            "Discovery", # hostname, whoami, pwd, cd traversal
            "Collection", # cat profiles.ini (Firefox profile config, path to bookmarks/history DB)
            "Command and Control", # HTTP C2 to ta1-pivot-2 (128.55.12.233:80) internal, via stage1 at 42.183.7.162:80
        ],
        # !! AMBIGUITY: phone C2 source IP is 128.55.12.166, not the target-table stated 128.55.12.114
        "labels": {
            "pidsmaker": [
                "pidsmaker/node_clearscope_e5_firefox_0517.csv",
                # "pidsmaker/node_clearscope_e5_lockwatch_0517.csv",
                # "pidsmaker/node_clearscope_e5_tester_0517.csv",
            ],
        },
        "host_uuid":"54FF20FC-635E-6455-F04F-EA4FA27EBC1E"
    },

    ("2019-05-17 14:34:00", "2019-05-17 14:36:00"): {
        "descrpt": "MyApp/AppStarter Micro APT prep BinFmt-Elevate driver loaded, C2 FAILED",
        "report_sec": "10.9 (clearscope_2 portion)",
        "tactics": [
            "Initial Access", # ssh user@.114, adb push a64.ko + msm_g711tlaw.ko
            "Execution", # insmod msm_g711tlaw.ko, mknod /dev/msm_g711tlaw, insmod a64.ko
            "Privilege Escalation", # BinFmt-Elevate driver installed and armed (/dev/msm_g711tlaw trigger)
            "Defense Evasion", # filenames impersonate Qualcomm audio driver
        ],
        "labels": {
            "pidsmaker": [
                # "pidsmaker/node_clearscope_e5_firefox_0517.csv",
                # "pidsmaker/node_clearscope_e5_lockwatch_0517.csv",
                # "pidsmaker/node_clearscope_e5_tester_0517.csv",
            ],
        },
        "host_uuid":"54FF20FC-635E-6455-F04F-EA4FA27EBC1E"
    },

    ("2019-05-17 15:43:00", "2019-05-17 16:00:00"): {
        "descrpt": "Lockwatch APK Java APT ELEVATE multi-DB exfil attempts",
        "report_sec": "10.10",
        "substantive": True,
        "tactics": [
            "Initial Access", # adb install lockwatch-instr.apk (after 2x failure + uninstall)
            "Execution", # am start com.bloketech.lockwatch/.MainActivity Java APT runs
            "Privilege Escalation", # ELEVATE command BinFmt-Elevate uid 0
            # "Defense Evasion", # Java-based can be regarded novel shape
            "Discovery", # SHELL ls /, SHELL whoami (pre- and post-elevate)
            # "Credential Access", # cp EmailProvider.db (attempted returned 0 bytes per ls -l)
            "Collection", # cp external.db, internal.db, lastAccess.db, calllog.db to /data/local/tmp
            "Command and Control", # Java APT C2 to ta1-pivot-2 (128.55.12.233:80) internal pivot
        ],
        "labels": {
            "pidsmaker": [
                # "pidsmaker/node_clearscope_e5_firefox_0517.csv",
                "pidsmaker/node_clearscope_e5_lockwatch_0517.csv",
                # "pidsmaker/node_clearscope_e5_tester_0517.csv",
            ],
        },
        "host_uuid":"54FF20FC-635E-6455-F04F-EA4FA27EBC1E"
    },

}

e5_fivedirections_1 = {
    ("2019-05-16 14:24:00", "2019-05-16 16:34:00"): {
        "descrpt": "Firefox BITS Verifier Drakon APT, BITS download, drop tester.exe",
        "report_sec": "9.4",
        "tactics": [
            "Initial Access", # Firefox backdoor exploit + BITS-via-backdoor (failed end-to-end delivery)
            # "Resource Development", # attacker-controlled infra: 215.237.119.171 (srv), 68.149.51.179 (BITS src), 170.32.78.39 (C2); dbgstat.dll / tester.exe staged
            "Execution", # tester.exe run as Administrator (SETUP!!); Drakon loaded into every Firefox
            "Persistence", # Application Verifier DLL hijack dbgstat.dll registered as verifier for firefox.exe, survives reboots & re-launches
            "Privilege Escalation", # Drakon runs as SYSTEM (inherited from Verifier injection context)
            "Defense Evasion", # Verifier abuse = legitimate Windows debug facility; DLL named dbgstat.dll to masquerade
            "Discovery", # hostname, whoami, ps auto-run via verscript on every callback
            "Command and Control", # verscript drives C2 callbackjs
        ],
        # NOTE 14:24 is when attacker first drove the BITS attack; 11:03 is reported as start in the section, but this is benign setup
        "labels": {},
        "host_uuid":"2AB88DCD-CBE6-41DF-AC69-9F6D6058E398",
    },

    ("2019-05-17 16:11:00", "2019-05-17 16:16:00"): {
        "descrpt": "Re-exploited Verifier Drakon APT FileFilter-Elevate",
        "report_sec": "10.11",
        "tactics": [
            "Execution", # Drakon (loaded via pre-existing Verifier persistence) + elevate3 command
            "Privilege Escalation", # FileFilter elevate driver
            "Defense Evasion", # reliance on pre-installed filemon.sys
            "Discovery", # whoami, hostname, ps, dir, cat hosts
            "Collection", # cat hosts (network topology info)
            # "Exfiltration", # hosts content returned over C2 (implicit exfil-over-C2-channel,)
            "Command and Control", # HTTP C2 to 170.32.78.39:80 (existing channel from 9.4)
        ],
        # NOTE: report 10.6.3 describes filemon driver install as Benign Activity Setup
        "labels": {
            "pidsmaker": [
                "pidsmaker/node_fivedirections_e5_drakon_0517.csv",
            ],
        },
        "host_uuid":"2AB88DCD-CBE6-41DF-AC69-9F6D6058E398"
    },
}


e5_fivedirections_2 = {
    ("2019-05-09 13:26:00", "2019-05-09 13:56:00"): {
        "descrpt": "Firefox Drakon APT + Elevate + Copykatz Sysinfo",
        "report_sec": "4.3",
        "tactics": [
            "Initial Access", # Firefox exploit via hijacked www.usdoj.gov
            # "Resource Development", # attacker infra: 77.138.117.150 (webserver), 150.159.104.124 (shellcode), 19.49.27.211 (C2)
            "Execution", # Drakon in Firefox memory; in-memory loaded modules (copykatz, sysinfo)
            "Privilege Escalation", # elevatepid '\\.\perfmon' to SYSTEM
            "Defense Evasion", # in-memory module load via Drakon (no file dropper); driver-based elevation
            "Credential Access", # Copykatz = Mimikatz equivalent
            "Discovery", # whoami, hostname, getpid, ls, sysinfo GetAllInfo
            "Collection", # reading dumped creds
            "Exfiltration", # s.o.
            "Command and Control", # HTTP C2 to 19.49.27.211:80
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_fivedirections_e5_copykatz_0509.csv"],
        },
        "host_uuid": "223CBBCE-1BC5-451E-9D2E-5B3A762F31C7"
    },

    ("2019-05-15 13:15:00", "2019-05-15 13:34:00"): {
        "descrpt": "Firefox BITS Micro APT",
        "report_sec": "8.4",
        "tactics": [
            "Initial Access", # Firefox backdoor
            # "Resource Development",
            "Execution", # ctfhost2.exe ran on target after BITS drop
            "Defense Evasion", # BITS Jobs; seems to be https://attack.mitre.org/techniques/T1197/
            "Discovery", # aptinfo, whoami, pwd, ls, screenshot
            "Collection", # screenshot
            "Exfiltration", # getfile hosts, getfile screenshot.png
            "Command and Control", # Micro APT TCP C2 to 113.165.213.253:80
            # Privilege Escalation failed
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_fivedirections_e5_bits_0515.csv"],
        },
        "host_uuid": "223CBBCE-1BC5-451E-9D2E-5B3A762F31C7"
    },
}

# 128.55.12.77
e5_fivedirections_3 = {
    ("2019-05-10 14:43:00", "2019-05-10 15:05:00"): {
        "descrpt": "SSH lateral-movement, exfild passwd then SSH'd onward to ta51-pivot-3.",
        "report_sec": "5.2",
        "tactics": [
            # no initial access by exploit, but normal ssh with creds (assumed stolen; this can not count as setup)
            "Lateral Movement", # SSH with stolen creds into this host
            "Execution", # cmd.exe session (SSH login on Windows), scp.exe, ssh.exe
            "Discovery", # dir, ipconfig, type hosts, cat drivers\etc\hosts
            "Collection", # passwd file read from C:\Users\admin
            "Exfiltration", # scp passwd to pivot-1
            "Command and Control", # ssh (?)
        ],
        "labels": {},
        "host_uuid":"552FFA2E-711A-488F-A65C-52762800923B", # used until 05-14, therefore different from other one
    },

    ("2019-05-17 12:47:00", "2019-05-17 13:04:00"): {
        "descrpt": "Firefox DNS Drakon APT FileFilter-Elevate",
        "report_sec": "10.6 / 10.7",
        "tactics": [
            "Initial Access", # Firefox backdoor via config.html click with DNS-channel shellcode
            # "Resource Development", # DNS channel domain (Xx--ls8h.com); # >>> C2 and Evasion
            "Execution", # Drakon loaded in Firefox; ran as SYSTEM from the start
            "Privilege Escalation", # pre-installed FileFilter-Elevate
            "Defense Evasion", # DNS channel as covert C2
            "Discovery", # hostname, whoami, ps, pwd, ls, cd sequences across filesystem
            "Collection", # cat passwd, cat hosts
            "Exfiltration", # passwd returned via Drakon
            "Command and Control", # C2
        ],
        "labels": {
            "pidsmaker": [
                "pidsmaker/node_fivedirections_e5_dns_0517.csv",
            ],
        },
        "host_uuid":"A8DB8613-F66E-4F0C-A19E-F43513BACC10",
    },
}

# ta1-marple-1 is at 128.55.12.66
e5_marple_1 = {
    ("2019-05-09 13:57:00", "2019-05-09 14:02:00"): {
        "descrpt": "Firefox Drakon APT via www.usdoj.gov hijack, elevation failed",
        "report_sec": "4.4",
        "tactics": [
            "Initial Access", # Firefox xploit delivered via hijacked www.usdoj.gov
            "Execution", # loaderDrakon in Firefox memory; sysinfo DLL module registered
            "Defense Evasion", # in-memory APT, no disk artifacts in this window
            "Discovery", # hostname, whoami, getpid (minimal; sysinfo-driven survey failed)
            "Command and Control", # HTTP C2
            # Privilege Escalation onyl attemped
        ],
        "labels": {},
        "host_uuid": "00000000-0000-0000-0000-000000000000"
    },

    ("2019-05-17 13:01:00", "2019-05-17 13:29:00"): {
        "descrpt": "Firefox DNS Drakon APT  file contents exfil over C2, elevation failed",
        "report_sec": "10.8",
        "tactics": [
            "Initial Access", # Firefox backdoor triggered via DNS lookup of Xx--ls8h.com
            "Execution", # loaderDrakon in Firefox memory
            "Defense Evasion", # DNS as C2 channel + in-memory
            "Discovery", # directory traversa, lsdir, ..
            "Collection", # cat passwd
            "Exfiltration", # s.o.
            "Command and Control", # HTTP C2
            # Privilege Escalation only
        ],
        "labels": {},
        "host_uuid": "00000000-0000-0000-0000-000000000000"
    },
}

# theia-1 128.55.12.110
e5_theia_1 = {
    ("2019-05-10 13:45:00", "2019-05-10 14:23:00"): {
        "descrpt": "Inbound SSH from cadets-1 (stolen creds); pivot to trace-2",
        "report_sec": "5.2",
        "tactics": [
            "Lateral Movement", # inbound ssh from ta1-cadets-1
            "Discovery", # ls, ifconfig, cat hosts, scp passwd admin@128.55.12.149
        ],
        "labels": {
        },
        "host_uuid":"37345038-89F2-5899-8FD2-B6D0844A7DBF"
    },

    ("2019-05-15 14:48:00", "2019-05-15 15:07:00"): {
        "descrpt": "Firefox Drakon APT + BinFmt-Elevate + Inject2 into sshd (2nd successful sshd inject of E5)",
        "report_sec": "8.6",
        "tactics": [
            "Initial Access", # Firefox exploit via www.nhra.com
            "Execution", # Drakon APT reflectively loaded in Firefox memory; sshd shellcode post-inject
            "Privilege Escalation", # elevate shm via BinFmt-Elevate drive sudo insmod load_helper.ko + read_scan.ko) returned uid 0 root
            "Defense Evasion", # in-memory loader
            "Persistence", # inject sc /e5/dist/sshd-linux-x64 into sshd
            "Discovery", # hostname, getpid, whoami, ps, cd /var/log, ls
            "Command and Control", # HTTP C2
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_THEIA_1_Firefox_Drakon_APT_BinFmt_Elevate_Inject.csv"],
        },
        "host_uuid":"37345038-89F2-5899-8FD2-B6D0844A7DBF"
    },
}

# TRACE-2 (ta1-trace-2, 128.55.12.118)
e5_trace_2 = {
    ("2019-05-10 14:22:00", "2019-05-10 14:42:00"): {
        "descrpt": "SSH login with stolen credentials, passwd file exfil via SCP",
        "report_sec": "5.2",
        "tactics": [
            "Lateral Movement", # SSH from ta1-theia-target-1 (128.55.12.110) into trace-2 using stolen creds
            "Credential Access", # stolen creds used for SSH auth
            "Collection", # passwd file present in home dir listed/accessed; scp passwd admin@128.55.12.149
            # "Exfiltration", # scp passwd admin@128.55.12.149:. — file exfiled to pivot host
            "Discovery", # ifconfig network interface enumeration
        ],
        "labels": {
            # "pidsmaker": ["pidsmaker/node_Trace_Firefox_Drakon.csv"],
        },
        "host_uuid":"DF4AF963-C31C-DAFC-B5C6-D86F33322775"
    },

    ("2019-05-14 10:18:00", "2019-05-14 10:28:00"): {
        "descrpt": "Firefox Drakon APT: exploit, elevate to root, inject into sshd (Day 1 active)",
        "report_sec": "7.3",
        "tactics": [
            "Initial Access", # Firefox backdoor exploit via hijacked www.yale.edu
            "Execution", # loaderDrakon executed in-memory in Firefox process; stage1 shellcode
            "Privilege Escalation", # BinFmt-Elevate driver: "elevate test" -> uid:0 root
            "Defense Evasion", # in-memory APT (no file on disk); inject into sshd replaces process context
            # "Discovery", # ps (found sshd PID 16808); whoami; hostname; pwd; getpid
            "Persistence", # inject into sshd PID 16808 — APT survives Firefox close; runs as root in sshd
            "Command and Control", # HTTP C2; L1 (Firefox) then L2 (sshd)
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Trace_Firefox_Drakon.csv"],
        },
        "host_uuid":"DF4AF963-C31C-DAFC-B5C6-D86F33322775"
    },

    ("2019-05-17 13:39:00", "2019-05-17 13:43:00"): {
        "descrpt": "Firefox Drakon APT: resumed sshd shell (Day 2 — L2 still alive from 05/14 inject)",
        "report_sec": "7.3 (20190517 Cont)",
        "tactics": [
            "Discovery", # whoami, hostname, pwd, ls, cd /home/admin, cd /etc, dir /etc
            "Collection", # cat passwd (??? freesbd format passwd ???)
            "Credential Access", # cat shadow
            "Command and Control", # continued use of L2 HTTP C2 channel (active since 05/14 10:21)
        ],
        "labels": {
            "pidsmaker": ["pidsmaker/node_Trace_Firefox_Drakon.csv"],
        },
        "host_uuid":"DF4AF963-C31C-DAFC-B5C6-D86F33322775"
    },

    # from report: We would consider all of this activity benign as no C2 connection ever happened
    ("2019-05-17 09:05:00", "2019-05-17 09:30:00"): {
        "descrpt": "Azazel rootkit deployment attempt — FAILED (no C2 achieved)",
        "report_sec": "10.3",
        "tactics": [
            "Initial Access",        # SCP of libselinux.so at 09:05; SSH login at 09:08 from 128.55.12.122
            # "Execution",             # fialed: export LD_PRELOAD=/lib/libselinux.so; nc/socat listeners
            # "Persistence",           # failed: LD_PRELOAD rootkit (Azazel) — would hook libc to hide itself
            # "Defense Evasion",       # failed: Azazel hooks functions; sudo mv to /lib/ (system path masquerade)
            "Discovery",             # ls /lib (confirms file placement); ls ~ (home dir contents); env; netstat
        ],
        "labels": {
            # "pidsmaker": ["pidsmaker/node_Trace_Firefox_Drakon.csv"],
        },
        "host_uuid":"DF4AF963-C31C-DAFC-B5C6-D86F33322775"
    },
}

# ta1-trace-1, 128.55.12.117)
e5_trace_1 = {
    ("2019-05-17 09:30:00", "2019-05-17 09:38:00"): {
        "descrpt": "Azazel rootkit deployment attempt — FAILED (no C2 achieved)",
        "report_sec": "10.3",
        "tactics": [
            "Initial Access",# SCP libselinux.so from bg-gen; SSH login from 128.55.12.122
            "Execution", # sudo mv to /lib/; export LD_PRELOAD; /bin/bash twice; socat/nc listeners
            # "Persistence", # failed LD_PRELOAD rootkit (Azazel) — hooks libc on new process launch
            # "Defense Evasion", # failed Azazel; sudo mv to /lib/ (system path masquerade)
            "Discovery",# ls ~; env; netstat
        ],
        "labels": {
            # "pidsmaker": ["pidsmaker/node_Trace_Firefox_Drakon.csv"],
        },
        "host_uuid":"7A665024-F3E3-3D4E-3A98-D9651E351DE4", # other uuid is never used
    },
}
