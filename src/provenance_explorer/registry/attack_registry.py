"""
DARPA Benchmark Attack Registries
- times are derived from the red team ground truth documents
- ground truth reports in EDT, data timestamps are in UTC
- if an attacjk steps end times are not documented, the end time is estimated from the next logged event
- Drakon  is an internal toolkit employed by the TA5 performers
"""
from datetime import datetime, timedelta, timezone

EDT = timezone(timedelta(hours=-4))
UTC = timezone.utc

def edt(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=EDT)

def to_utc(dt_edt):
    return dt_edt.astimezone(UTC)

def attack_step(start_edt, end_edt, description, tactic, label_files=None):
    return {
        "start_edt": start_edt,
        "end_edt": end_edt,
        "start_utc": to_utc(start_edt),
        "end_utc": to_utc(end_edt),
        "description": description,
        "tactic": tactic,
        "label_files": label_files or {},
    }

# PIDSMaker / Orthrus
PM = "pidsmaker"
# Flash / ThreaTrace
FL = "flash"
# What We Talk About When We Talk About Logs
WW = "wwtawwtal"
# Revisiting DARPA optc
RV = "revisiting_optc"

# e3 04-06 to 04–13, 2018
E3_CADETS = {
    "dataset": "e3",
    "subdataset": "CADETS",
    "os": "FreeBSD",
    "host": "ta1-cadets-1",
    "description": (
        "FreeBSD server (Nginx) and Postfix email server for the Bovia compamny network."
        "APT-ish attacker repeatedly exploited Nginx; process injection into sshd failed every time causing kernel panics."
        "served as email relay for all Common Threat phishing campaigns."
    ),
    "attacks": [
        # 3.1 2018-04-06 11:00 Nginx Backdoor #1
        attack_step(
            edt(2018, 4, 6, 11, 21), edt(2018, 4, 6, 11, 22),
            "Exploit Nginx via malformed HTTP POST (first fails, second succeeds)",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_06.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 6, 11, 22), edt(2018, 4, 6, 11, 33),
            "loaderDrakon in Nginx memory, C2 callback established",
            "Execution",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_06.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 6, 11, 33), edt(2018, 4, 6, 11, 38),
            "Elevate drakon as new root process",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_06.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 6, 11, 38), edt(2018, 4, 6, 11, 42),
            "Netrecon module: network interface scan (nrtcp to 2 addresses)",
            "Discovery",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_06.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 6, 12, 4), edt(2018, 4, 6, 12, 8),
            "Download libdrakon to /var/log/devc, attempt inject into sshd PID 809",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_06.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 6, 12, 8), edt(2018, 4, 6, 12, 10),
            "Inject into sshd fails -> kernel panic, connection lost",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_06.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),

        # 3.8 2018-04-11 1500 Nginx Backdoor #2 
        attack_step(
            edt(2018, 4, 11, 15, 8), edt(2018, 4, 11, 15, 10),
            "Re-exploit Nginx via HTTP POST",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_11.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 15, 10), edt(2018, 4, 11, 15, 12),
            "Download libdrakon to /tmp/grain (putfile to sendmail failed first)",
            "Persistence",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_11.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 15, 15), edt(2018, 4, 11, 15, 15),
            "Inject /tmp/grain into sshd PID 802 -> kernel panic",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_11.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),

        # 3.13 2018-04-12 1400 Nginx Backdoor #3 + Micro APT 
        attack_step(
            edt(2018, 4, 12, 14, 0), edt(2018, 4, 12, 14, 2),
            "Re-exploit Nginx, shell F1 established",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_12.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 12, 14, 2), edt(2018, 4, 12, 14, 12),
            "Multiple elevate attempts for micro APT (mostly failed), elevate drakon XIM succeeds",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_12.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 12, 14, 12), edt(2018, 4, 12, 14, 37),
            "Deploy micro APT (sendmail/test), execute, port scan 8 hosts",
            "Discovery",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_12.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),

        #  3.14  20180413 Nginx Backdoor #4 
        attack_step(
            edt(2018, 4, 13, 9, 4), edt(2018, 4, 13, 9, 7),
            "Reconnect to left-open connection, disconnect, re-exploit Nginx",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_13.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 9, 10), edt(2018, 4, 13, 9, 12),
            "Deploy drakon + libdrakon to disk, elevate drakon as root",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_Nginx_Backdoor_13.csv"],
                FL: ["flash/cadets.json"],
                WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 9, 13), edt(2018, 4, 13, 9, 15),
            "Inject into sshd PID 20691 (3 attempts: memhelp.so, eraseme, done.so) -> all fail",
            "Defense Evasion",
            {PM: ["pidsmaker/node_Nginx_Backdoor_13.csv"],
             FL: ["flash/cadets.json"],
             WW: ["wwtawwtal/cadets_labels.csv", "wwtawwtal/cadets_edge_labels.csv"]}
        ),

        # 4.1 Common Threat: CADETS as email relay
        attack_step(
            edt(2018, 4, 6, 14, 40), edt(2018, 4, 6, 15, 2),
            "Common Threat sends phishing emails to ClearScope via CADETS postfix",
            "Initial Access",
            # likely no label files for email relay 
        ),
        attack_step(
            edt(2018, 4, 9, 13, 19), edt(2018, 4, 9, 14, 19),
            "Common Threat sends phishing emails to TA5.2/FiveD via CADETS postfix",
            "Initial Access",
            # ...
        ),
        attack_step(
            edt(2018, 4, 10, 12, 28), edt(2018, 4, 10, 12, 30),
            "Common Threat sends phishing email to everyone@bovia.com via CADETS postfix",
            "Initial Access",
            # ...
        ),
    ],
}

E3_TRACE = {
    "dataset": "e3",
    "subdataset": "TRACE",
    "os": "Ubuntu 14.04",
    "host": "ta1-trace-1",
    "description": (
        "development host. Firefox exploited via malicious ads."
        "Drakon APT deployed in memory and a Pine backdoor with auto-executing attachments."
    ),
    "attacks": [
        # 3.2  2018-04-10 10:00 Firefox Backdoor 
        attack_step(
            edt(2018, 4, 10, 9, 46), edt(2018, 4, 10, 10, 49),
            "Exploit Firefox 54.0.1 via malicious ad on allstate.com (crashes, eventually succeeds)",
            "Initial Access",
            {
                PM: ["pidsmaker/node_trace_e3_firefox_0410.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 10, 49), edt(2018, 4, 10, 10, 51),
            "Drakon in Firefox memory, 2 connections to C2",
            "Execution",
            {
                PM: ["pidsmaker/node_trace_e3_firefox_0410.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 10, 51), edt(2018, 4, 10, 10, 53),
            "Elevate drakon as root, close non-root shells",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_trace_e3_firefox_0410.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 11, 9), edt(2018, 4, 10, 11, 10),
            "Write libdrakon to /var/log/xtmp for later use",
            "Persistence",
            {
                PM: ["pidsmaker/node_trace_e3_firefox_0410.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 12, 28), edt(2018, 4, 10, 12, 35),
            "Phishing email link opened (nasa.ng), credentials submitted to foo1.com",
            "Credential Access",
            # unlikely labeled
        ),
        attack_step(
            edt(2018, 4, 12, 13, 36), edt(2018, 4, 12, 13, 36),
            "Browser extension exploit via allstate.com — Firefox hangs, no callback",
            "Initial Access",
            # Failed attack, unlikely labeled
        ),
        attack_step(
            edt(2018, 4, 13, 12, 43), edt(2018, 4, 13, 12, 46),
            "Browser ext. dropper via allstate.com, drakon written to disk and executed",
            "Execution",
            {
                PM: ["pidsmaker/node_trace_e3_pine_0413.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 12, 46), edt(2018, 4, 13, 12, 48),
            "Deploy micro APT (ztmp), attempt elevate (fails), execute as user",
            "Execution",
            {
                PM: ["pidsmaker/node_trace_e3_pine_0413.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 12, 48), edt(2018, 4, 13, 12, 53),
            "Micro APT port scan (no open ports found), netrecon",
            "Discovery",
            {
                PM: ["pidsmaker/node_trace_e3_pine_0413.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 13, 50), edt(2018, 4, 13, 14, 2),
            "Phishing email with tcexec executable, fails (missing library)",
            "Initial Access",
            {   
                PM: ["pidsmaker/node_trace_e3_phishing_executable_0413.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 14, 10), edt(2018, 4, 13, 14, 15),
            "Restart vulnerable Pine, send micro APT as attachment",
            "Execution",
            {   
                PM: ["pidsmaker/node_trace_e3_phishing_executable_0413.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 14, 20), edt(2018, 4, 13, 14, 28),
            "Pine auto-runs micro APT, port scan, shell attempts fail",
            "Discovery",
            {
                PM: ["pidsmaker/node_trace_e3_phishing_executable_0413.csv"],
                FL: ["flash/trace.json"],
                WW: ["wwtawwtal/trace_labels.csv"]
            }
        ),
    ],
}

E3_THEIA = {
    "dataset": "e3",
    "subdataset": "theia",
    "os": "Ubuntu 12.04",
    "host": "ta1-theia-1",
    "description": (
        "development host. "
        "Firefox exploited via malicious ads. Significant stability issues (unresponsiveness, reboots). "
        "Browser extension successfully deployed micro APT for port scanning."
    ),
    "attacks": [
        attack_step(
            edt(2018, 4, 10, 13, 41), edt(2018, 4, 10, 14, 31),
            "Exploit Firefox via malicious ad on allstate.com (3 crashes), re-exploit via gatech.edu",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Firefox_Backdoor_Drakon_In_Memory.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 14, 31), edt(2018, 4, 10, 14, 35),
            "Shell from THEIA, putfile clean, elevate as root",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_Firefox_Backdoor_Drakon_In_Memory.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 14, 51), edt(2018, 4, 10, 14, 55),
            "Root drakon stops responding, re-exploit gatech.edu",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Firefox_Backdoor_Drakon_In_Memory.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 14, 55), edt(2018, 4, 10, 15, 0),
            "Write libdrakon to /var/log/xdev, leave connection open",
            "Persistence",
            {
                PM: ["pidsmaker/node_Firefox_Backdoor_Drakon_In_Memory.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 10, 13, 42), edt(2018, 4, 10, 13, 50),
            "Phishing email link opened (nasa.ng), credentials submitted to foo1.com",
            "Credential Access",
        ),
        attack_step(
            edt(2018, 4, 12, 12, 44), edt(2018, 4, 12, 12, 51),
            "Browser ext. dropper via gatech.edu, drakon written to disk and executed",
            "Execution",
            {
                PM: ["pidsmaker/node_Browser_Extension_Drakon_Dropper.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 12, 12, 53), edt(2018, 4, 12, 13, 9),
            "Attempt inject xdev/wdev/memtrace.so into sshd (all fail)",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_Browser_Extension_Drakon_Dropper.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 12, 13, 17), edt(2018, 4, 12, 13, 26),
            "Deploy micro APT (mail), elevate, port scan 10 hosts",
            "Discovery",
            {
                PM: ["pidsmaker/node_Browser_Extension_Drakon_Dropper.csv"],
                FL: ["flash/theia.json"],
                WW: ["wwtawwtal/theia_labels.csv", "wwtawwtal/theia_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 13, 13, 50), edt(2018, 4, 13, 14, 4),
            "Phishing email with tcexec executable, downloaded and run — fails (missing library)",
            "Initial Access",
        ),
    ],
}

E3_FIVEDIRECTIONS = {
    "dataset": "e3",
    "subdataset": "fivedirections",
    "os": "Windows 10",
    "host": "ta1-fivedirections-1",
    "description": (
        "Firefox exploited via cnpc.com.cn. "
        "Common Threat used Excel macro with PowerShell stager."
    ),
    "attacks": [
        attack_step(
            edt(2018, 4, 11, 10, 0), edt(2018, 4, 11, 10, 9),
            "Exploit Firefox 54.0.1 via cnpc.com.cn (multiple crashes, eventually connects)",
            "Initial Access",
            {
                PM: ["pidsmaker/node_fivedirections_e3_firefox_0411.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 10, 15), edt(2018, 4, 11, 10, 15),
            "Netrecon module loaded, TCP exfil to 193.189.212.26:80",
            "Discovery",
            {
                PM: ["pidsmaker/node_fivedirections_e3_firefox_0411.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 10, 15), edt(2018, 4, 11, 10, 39),
            "Exfiltrate documents (trains.rtf, malicious.rtf, Covert.xlsx, etc.)",
            "Exfiltration",
            {
                PM: ["pidsmaker/node_fivedirections_e3_firefox_0411.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 10, 40), edt(2018, 4, 11, 10, 40),
            "Netrecon UDP exfil attempt fails, Firefox crashes — connection lost",
            "Exfiltration",
            {
                PM: ["pidsmaker/node_fivedirections_e3_firefox_0411.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 9, 13, 19), edt(2018, 4, 9, 14, 49),
            "Phishing email with BoviaBenefitsOE.xlsm sent, macro fails to auto-execute",
            "Initial Access",
            {
                PM: ["pidsmaker/node_fivedirections_e3_excel_0409.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 9, 15, 7), edt(2018, 4, 9, 15, 42),
            "PowerShell command executed manually, reverse shell via powercat, file survey",
            "Execution",
            {
                PM: ["pidsmaker/node_fivedirections_e3_excel_0409.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 12, 11, 13), edt(2018, 4, 12, 11, 14),
            "Browser ext. dropper via allstate.com — drakon crashes on Windows 10",
            "Execution",
            {
                PM: ["pidsmaker/node_fivedirections_e3_browser_0412.csv"],
                FL: ["flash/fivedirections.json"],
                WW: ["wwtawwtal/fivedirections_labels.csv", "wwtawwtal/fivedirections_edge_labels.csv"]
            }
        ),
    ],
}

E3_CLEARSCOPE = {
    "dataset": "e3",
    "subdataset": "clearscope",
    "os": "Android 6.0.1",
    "host": "ta1-clearscope-1",
    "description": (
        "Firefox exploited via mit.gov.jo. Module loading failed unexpectedly. "
        "Phishing for credential harvest."
        "Metasploit APK repeatedly failed."
    ),
    "attacks": [
        attack_step(
            edt(2018, 4, 11, 13, 55), edt(2018, 4, 11, 14, 20),
            "Exploit Firefox on Android via mit.gov.jo (first succeeds, benign activity closes browser, re-exploit)",
            "Initial Access",
            {
                PM: ["pidsmaker/node_clearscope_e3_firefox_0411.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 14, 22), edt(2018, 4, 11, 14, 22),
            "Elevate drakon to root process",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_clearscope_e3_firefox_0411.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 11, 14, 26), edt(2018, 4, 11, 14, 47),
            "Netrecon fails, inject into installd PID 424 fails",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_clearscope_e3_firefox_0411.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 12, 15, 19), edt(2018, 4, 12, 15, 24),
            "Continue via left-open connection, retry inject sshd (fail), elevate new drakon (L5)",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_clearscope_e3_firefox_0412.csv"]
            }
        ),
        attack_step(
            edt(2018, 4, 6, 15, 2), edt(2018, 4, 6, 15, 17),
            "Phishing email with link to nasa.ng, Bob enters credentials, submitted to foo1.com",
            "Credential Access",
            # No labels
        ),
        attack_step(
            edt(2018, 4, 13, 10, 28), edt(2018, 4, 13, 12, 0),
            "Metasploit apk installed and user clicked  repeatedly, meterpreter never delivers; unkn wn reasons ",
            "Initial Access",
            # failed attack
        ),
        attack_step(
            edt(2018, 4, 13, 13, 3), edt(2018, 4, 13, 14, 15),
            "MetaApp installed, more attempts, all fail",
            "Initial Access",
            # s.o.
        ),
    ],
}


# E5 05-08 to 05-17 2019)
E5_CADETS = {
    "dataset": "e5",
    "subdataset": "cadets",
    "os": "FreeBSD",
    "host": "ta1-cadets-1/2",
    "description": (
        "FreeBSD hosts attacked on May 16 and 17 via Nginx backdoor with Drakon APT. "
        "Privilege escalation succeeded in E5."
    ),
    "attacks": [
        attack_step(
            edt(2019, 5, 16, 9, 32), edt(2019, 5, 16, 10, 30),
            "Exploit Nginx on CADETS 1 and 2, Drakon APT in memory, elevate to root",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Nginx_Drakon_APT.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 10, 16), edt(2019, 5, 17, 11, 0),
            "Re-exploit Nginx on CADETS 1 and 2, Drakon APT with persistence",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Nginx_Drakon_APT_17.csv"]
            }
        ),
    ],
}

E5_TRACE = {
    "dataset": "e5",
    "subdataset": "trace",
    "os": "Ubuntu 14.04",
    "host": "ta1-trace-2",
    "description": (
        "Linux host attacked May 14 and 17. Firefox Drakon APT with successful binfmt-based privilege escalation and sshd injection."
    ),
    "attacks": [
        attack_step(
            edt(2019, 5, 14, 10, 8), edt(2019, 5, 14, 11, 30),
            "Firefox Drakon APT, binfmt-elevate to root, inject into sshd, read /etc/passwd + shadow, exfil documents",
            "Initial Access",
            {
                PM: ["pidsmaker/node_Trace_Firefox_Drakon.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 9, 5), edt(2019, 5, 17, 10, 0),
            "Azazel rootkit deployment attempt on TRACE 1 and 2 — failed",
            "Defense Evasion",
            # failed, likely no labels
        ),
    ],
}

E5_THEIA = {
    "dataset": "e5",
    "subdataset": "theia",
    "os": "Ubuntu 12.04/14.04",
    "host": "ta1-theia-1/2/3",
    "description": (
        "Linux host. Firefox Drakon APT failed on May 14, succeeded on May 15 with BinFmt-Elevate and sshd injection."
    ),
    "attacks": [
        attack_step(
            edt(2019, 5, 14, 11, 45), edt(2019, 5, 14, 12, 0),
            "Firefox Drakon APT on THEIA; failed (no shell)",
            "Initial Access",
            # likely none
        ),
        attack_step(
            edt(2019, 5, 14, 20, 32), edt(2019, 5, 14, 21, 0),
            "install binfmt elevate driver on THEIA 3 for later use",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_THEIA_1_Firefox_Drakon_APT_BinFmt_Elevate_Inject.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 15, 14, 48), edt(2019, 5, 15, 15, 30),
            "Firefox Drakon APT, binfmt-elevate to root, inject libdrakon into sshd",
            "Initial Access",
            {
                PM: ["pidsmaker/node_THEIA_1_Firefox_Drakon_APT_BinFmt_Elevate_Inject.csv"]
            }
        ),
    ],
}

E5_FIVEDIRECTIONS = {
    "dataset": "e5",
    "subdataset": "fivedirections",
    "os": "Windows 10",
    "host": "ta1-fivedirections-1/2/3",
    "description": (
        "Windows 10 hosts attacked on May 9, 15, 16, 17 with Drakon APT:;"
        "incl. Copykatz (Mimikatz), BITS download, Verifier, DNS C2, FileFilter-Elevate."
    ),
    "attacks": [
        attack_step(
            edt(2019, 5, 9, 13, 26), edt(2019, 5, 9, 13, 56),
            "Firefox Drakon APT via usdoj.gov, elevate to SYSTEM, Copykatz credential harvest, Sysinfo",
            "Initial Access",
            {
                PM: ["pidsmaker/node_fivedirections_e5_copykatz_0509.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 15, 13, 15), edt(2019, 5, 15, 14, 0),
            "Firefox BITS download of Micro APT (ctfhost2.exe), C2 callback, recon",
            "Execution",
            {
                PM: ["pidsmaker/node_fivedirections_e5_bits_0515.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 16, 11, 3), edt(2019, 5, 16, 12, 0),
            "Firefox BITS Verifier Drakon APT on FiveDirections 1",
            "Initial Access",
            {
                PM: ["pidsmaker/node_fivedirections_e5_drakon_0517.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 12, 26), edt(2019, 5, 17, 13, 0),
            "Firefox DNS Drakon APT with FileFilter-Elevate on FiveDirections 3",
            "Initial Access",
            {
                PM: ["pidsmaker/node_fivedirections_e5_dns_0517.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 16, 11), edt(2019, 5, 17, 16, 30),
            "Continuation of Verifier Drakon APT on FiveDirections 1",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_fivedirections_e5_drakon_0517.csv"]
            }
        ),
    ],
}

E5_CLEARSCOPE = {
    "dataset": "e5",
    "subdataset": "clearscope",
    "os": "Android",
    "host": "ta1-clearscope-1/2",
    "description": (
        "Android hosts attacked across May 13-17; most attacks failed. "
        "Successful: Appstarter APK, Firefox Drakon APT, Lockwatch APK, Tester Micro APT."
    ),
    "attacks": [
        attack_step(
            edt(2019, 5, 13, 10, 26), edt(2019, 5, 13, 12, 0),
            "Metasploit APK install on ClearScope — partial success (sessions unstable)",
            "Initial Access",
            # löikely no labels 
        ),
        attack_step(
            edt(2019, 5, 15, 15, 39), edt(2019, 5, 15, 16, 30),
            "Appstarter APK installs Micro APT, binfmt-elevate to root",
            "Initial Access",
            {
                PM: ["pidsmaker/node_clearscope_e5_appstarter_0515.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 11, 50), edt(2019, 5, 17, 12, 20),
            "Firefox Drakon APT on ClearScope 2",
            "Initial Access",
            {
                PM: ["pidsmaker/node_clearscope_e5_firefox_0517.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 15, 43), edt(2019, 5, 17, 16, 10),
            "Lockwatch APK installs Java APT on ClearScope 2",
            "Persistence",
            {
                PM: ["pidsmaker/node_clearscope_e5_lockwatch_0517.csv"]
            }
        ),
        attack_step(
            edt(2019, 5, 17, 16, 20), edt(2019, 5, 17, 16, 45),
            "Tester Micro APT with BinFmt-Elevate on ClearScope 1",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_clearscope_e5_tester_0517.csv"]
            }
        ),
    ],
}

E5_MARPLE = {
    "dataset": "e5",
    "subdataset": "marple",
    "os": "Windows 7",
    "host": "ta1-marple-1",
    "description": (
        "May 9: Firefox Drakon APT, elevate failed, becaus edriver signing re-enabled)."
        "May 17: Firefox DNS Drakon APT succeeded."
    ),
    "attacks": [
        attack_step(
            edt(2019, 5, 9, 13, 57), edt(2019, 5, 9, 14, 2),
            "Firefox Drakon APT via usdoj.gov, elevate fails (driver signing enabled), sysinfo fails",
            "Initial Access",
            # No labels available for Marple
        ),
        attack_step(
            edt(2019, 5, 17, 13, 1), edt(2019, 5, 17, 13, 30),
            "Firefox DNS Drakon APT on MARPLE 1",
            "Initial Access",
            # s.o.
        ),
    ],
}


# optc 09-23 to 09–25, 2019
OPTC_AIA_201_225 = {
    "dataset": "optc",
    "subdataset": "aia_201_225",
    "os": "Windows 10 (Enterprise domain)",
    "host": "Sysclient0201 (primary), Sysclient0205 (pivot target)",
    "description": (
        "Day 1 primary entry point. Plain PowerShell Empire. UAC bypass, Mimikatz, lateral movement via WMI to 0402/0660/DC1, then spread to 14 stations including 0205."
    ),
    "attacks": [
        attack_step(
            edt(2019, 9, 23, 11, 23), edt(2019, 9, 23, 11, 24),
            "Download runme.bat (PS Empire stager) via Firefox on Sysclient0201",
            "Initial Access",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 11, 24), edt(2019, 9, 23, 11, 26),
            "PS Empire agent VL8B5T3U checks in, delete runme.bat",
            "Execution",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 11, 26), edt(2019, 9, 23, 11, 26),
            "UAC bypass via registry modification (windir/Environment), elevated agent LUAVR71T",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 11, 33), edt(2019, 9, 23, 11, 35),
            "Mimikatz credential dump, obtain zleazer password",
            "Credential Access",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 11, 37), edt(2019, 9, 23, 11, 42),
            "PSInject into LSASS (fails), retry (fails)",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 11, 39), edt(2019, 9, 23, 11, 39),
            "Establish persistence: HKCU CurrentVersion\\Debug registry key",
            "Persistence",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 12, 51), edt(2019, 9, 23, 12, 52),
            "Screenshot of desktop",
            "Collection",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 12, 58), edt(2019, 9, 23, 13, 15),
            "ARP scan, SMB test, ping sweep of 142.20.56.0/24",
            "Discovery",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 13, 24), edt(2019, 9, 23, 13, 25),
            "WMI pivot to Sysclient0402",
            "Lateral Movement",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 14, 6), edt(2019, 9, 23, 14, 6),
            "kill agent on Sysclient0201",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_h201_0923.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        # mass spread
        attack_step(
            edt(2019, 9, 23, 14, 45), edt(2019, 9, 23, 15, 24),
            "WMI spread from DC1 to 14 stations (incl. Sysclient0205), then kill all agents",
            "Lateral Movement",
            {
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 23, 15, 30), edt(2019, 9, 23, 15, 30),
            "Remove registry persistence on Sysclient0201",
            "Defense Evasion",
            {
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
    ],
}

OPTC_AIA_501_525 = {
    "dataset": "optc",
    "subdataset": "aia_501_525",
    "os": "Windows 10 (Enterprise domain)",
    "host": "Sysclient0501 (primary Day 2), Sysclient0503 (Day 1 pivot target)",
    "description": (
        "Day 1: 0503 received WMI agent from DC1."
        "Day 2 primary target. Custom PS Empire . Phishing with macroless Word doc. "
        "DeathStar domain takeover;RDP tunneling via plink for data exfiltration. "
    ),
    "attacks": [
        # Day 1: Sysclient0503 (in 501-525 range) hit by WMI spread
        attack_step(
            edt(2019, 9, 23, 14, 45), edt(2019, 9, 23, 15, 24),
            "Sysclient0503: WMI pivot from DC1 (Day 1 mass spread), agent deployed + killed",
            "Lateral Movement",
            {
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 10, 28), edt(2019, 9, 24, 10, 36),
            "Sysclient0501; Phishing email with malicious payroll.docx to bantonio@systemia.com",
            "Initial Access",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 10, 36), edt(2019, 9, 24, 10, 46),
            "Sysclient0501; PS Empire agent K3G1U8DN via macroless doc",
            "Execution",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 10, 46), edt(2019, 9, 24, 10, 51),
            "Sysclient0501; Pivot to custom PS Empire on sports.com:443, agent 4BW2MKUF",
            "Command and Control",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 11, 3), edt(2019, 9, 24, 11, 20),
            "Sysclient0501; DeathStar: domain enumeration, find DCs, lateral movement, obtain DC1 agent",
            "Discovery",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 11, 23), edt(2019, 9, 24, 11, 33),
            "Sysclient0501; UAC bypass attempts (fail), obtain elevated agent via DC1 WMI with admin creds",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 11, 34), edt(2019, 9, 24, 11, 34),
            "Sysclient0501; WMI persistence subscription: callback at 10:00 daily or within 5min of boot",
            "Persistence",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 11, 37), edt(2019, 9, 24, 11, 45),
            "Sysclient0501; Winenum (keyword: important,secret,classified), privesc vector check, findtrusteddocuments",
            "Collection",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 11, 45), edt(2019, 9, 24, 13, 11),
            "Sysclient0501; Upload plink.exe, establish reverse SSH tunnel for RDP port forwarding",
            "Command and Control",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 13, 19), edt(2019, 9, 24, 13, 26),
            "Sysclient0501; RDP into host, download nc.exe (fileTransfer1000.exe) via Chrome",
            "Lateral Movement",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 13, 31), edt(2019, 9, 24, 13, 45),
            "Sysclient0501; Compress C:\\documents, exfiltrate export.zip via nc to news.com:9999, cleanup",
            "Exfiltration",
            {PM: ["pidsmaker/node_h501_0924.csv"],
             FL: ["flash/optc.txt"],
             RV: ["revisiting_optc/malicious.json"]}
        ),
        attack_step(
            edt(2019, 9, 24, 13, 46), edt(2019, 9, 24, 15, 28),
            "Sysclient0501; RDP pivot to 0974, then 0005; mount share, exfil 3.5GB allgone.zip, cleanup",
            "Exfiltration",
            {
                PM: ["pidsmaker/node_h501_0924.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 24, 15, 42), edt(2019, 9, 24, 15, 45),
            "Spread to 6 workstations overnight via DC1 (incl. 0010, 0069, 0203, 0358, 0618, 0851)",
            "Lateral Movement",
            {
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
    ],
}

OPTC_AIA_51_75 = {
    "dataset": "optc",
    "subdataset": "aia_51_75",
    "os": "Windows 10 (Enterprise domain)",
    "host": "Sysclient0051 (primary Day 3), Sysclient0069 (Day 2 overnight)",
    "description": (
        "Day 2 overnight: 0069 received WMI agent from DC1."
        "Day 3: malicious Notepad++ update delivers Meterpreter on 0051; discovery, Mimikatz, persistence via autorun + timestomp, RDP. "
    ),
    "attacks": [
        # Day 2 overnight: 0069 in range
        attack_step(
            edt(2019, 9, 24, 15, 42), edt(2019, 9, 25, 9, 0),
            "Sysclient0069; WMI agent from DC1 (Day 2 overnight spread), runs until morning",
            "Lateral Movement",
            {
                RV: ["revisiting_optc/malicious.json"] # possibly
            }
        ),
        # Day 3 on 
        attack_step(
            edt(2019, 9, 25, 10, 29), edt(2019, 9, 25, 10, 31),
            "Sysclient0051; Malicious Notepad++ update downloads update.exe (Meterpreter reverse TCP)",
            "Initial Access",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 10, 31), edt(2019, 9, 25, 10, 32),
            "Sysclient0051; Meterpreter get_system via named pipe impersonation",
            "Privilege Escalation",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 10, 32), edt(2019, 9, 25, 10, 38),
            "Sysclient0051; CMD shell recon, ARP scan /22, enum applications/domain/shares",
            "Discovery",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 10, 40), edt(2019, 9, 25, 10, 44),
            "Sysclient0051; Migrate from cKfGW.exe (PID 2712) to LSASS (PID 568)",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 10, 44), edt(2019, 9, 25, 10, 48),
            "Sysclient0051; Mimikatz credential dump (cleartext passwords + hashes)",
            "Credential Access",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 10, 48), edt(2019, 9, 25, 10, 53),
            "Sysclient0051; Persistence: autorun registry + VBS script in C:\\Windows\\TEMP",
            "Persistence",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 10, 53), edt(2019, 9, 25, 11, 7),
            "Sysclient0051; Timestomp files in C:\\Windows\\TEMP, add admin user for RDP",
            "Defense Evasion",
            {
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
        attack_step(
            edt(2019, 9, 25, 13, 42), edt(2019, 9, 25, 14, 24),
            "Sysclient0051; RDP from attacker server, rerun update.exe",
            "Lateral Movement",
            {  
                PM: ["pidsmaker/node_h051_0925.csv"],
                FL: ["flash/optc.txt"],
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
    ],
}

# i included this range as a reference barely touched by attacks
OPTC_AIA_951_975 = {
    "dataset": "optc",
    "subdataset": "aia_951_975",
    "os": "Windows 10 (Enterprise domain)",
    "host": "Sysclient0955",
    "description": (
        "Only Sysclient0955 was touched during Day 1 mass deployment."
    ),
    "attacks": [
        attack_step(
            edt(2019, 9, 23, 14, 45), edt(2019, 9, 23, 15, 24),
            "Sysclient0955: WMI agent from DC1 (Day 1 mass spread), deployed + killed",
            "Lateral Movement",
            {
                RV: ["revisiting_optc/malicious.json"]
            }
        ),
    ],
}


ALL_REGISTRIES = {
    ("e3","cadets"): E3_CADETS,
    ("e3","trace"): E3_TRACE,
    ("e3","theia"): E3_THEIA,
    ("e3","fivedirections"): E3_FIVEDIRECTIONS,
    ("e3","clearscope"): E3_CLEARSCOPE,
    ("e5","cadets"): E5_CADETS,
    ("e5","trace"): E5_TRACE,
    ("e5","theia"): E5_THEIA,
    ("e5","fivedirections"): E5_FIVEDIRECTIONS,
    ("e5","clearscope"): E5_CLEARSCOPE,
    ("e5","marple"): E5_MARPLE,
    ("optc","aia_51_75"): OPTC_AIA_51_75,
    ("optc","aia_201_225"): OPTC_AIA_201_225,
    ("optc","aia_501_525"): OPTC_AIA_501_525,
    ("optc","aia_951_975"): OPTC_AIA_951_975,
}