# from OpTC ground truth file
#
# (start, end) of active attacker interaction only
# times ae UTC -4 and need to be converted to the actual timestamps like so
# t_start = date_string_to_ns_timestamp(
#     "2018-04-10 14:30:00", tz=timezone(timedelta(hours=-4))
# )

optc_sysclient0201 = {
    ("2019-09-23 11:23:29", "2019-09-23 15:30:00"): {
        "descrpt": "Initial compromise: malicious batch file download, UAC bypass, mimikatz, persistence, recon, pivot out to 0402",
        "report_sec": "Day 1",
        "tactics": [
            "Initial Access", # manual console access, downloaded runme.bat from news.com:8000
            "Execution", # ran PowerShell Empire stager (batch file); PowerShell throughout
            "Privilege Escalation", # bypassuac: registry mod of "windir" in "Environment"; elevated agent LUAVR71T
            "Credential Access", # mimikatz cleartext passwords; obtained creds for systemia.com\zleazer
            "Defense Evasion", # deleted runme.bat at 11:24:19; UAC bypass; psinject attempts (failed)
            "Persistence", # registry key HKCU:...\CurrentVersion\Debug (set 11:39, removed 15:30)
            "Discovery", # ps (process listing); ARP scan /22; ping sweep /24; SMB probe
            "Collection", # screenshot of desktop at 12:51:59
            "Lateral Movement", # invoke_wmi pivot to Sysclient0402 at 13:24:36
            "Command and Control", # PSE agent VL8B5T3U then LUAVR71T -> news.com:80 (132.197.158.98)
        ],
    },
}

optc_sysclient0501 = {
    ("2019-09-24 10:36:51", "2019-09-24 15:28:36"): {
        "descrpt": "Phishing entry point: macro-less Word doc, DeathStar domain enum, persistence, plink SSH tunnel, RDP pivot, data exfil",
        "report_sec": "Day 2",
        "tactics": [
            "Initial Access", # phishing email with payroll.docx (macro-less stager) from sgerard@ameblo.jp
            "Execution", # PowerShell Empire stager; multiple agents; DeathStar automation
            "Defense Evasion", # pivot to second C2 (sports.com:443 HTTPS); killed initial agent; UAC bypass attempts
            "Discovery", # DeathStar: domain SID, 43 domain admins, domain controllers, admin to 1025 hosts, GPP SYSVOL
            "Privilege Escalation", # bypassuac_eventvwr (DeathStar); invoke_wmi localhost; elevated agent via DC1 creds
            "Credential Access", # GPP SYSVOL privesc (credentials in GPOs)
            "Lateral Movement", # DeathStar lateral movement; invoke_wmi to DC1; DC1 pivots back to 0501 with admin creds
            "Persistence", # WMI subscription: callback at 10:00 daily or within 5 min of boot
            "Collection", # findtrusteddocuments; winenum with keywords "important,secret,classified"; compressed C:\documents
            "Exfiltration", # export.zip exfiled to news.com:9999 via nc.exe (fileTransfer1000.exe)
            "Command and Control", # sports.com:443 (202.6.172.98); plink reverse SSH tunnel; RDP via forwarded port
        ],
        # NOTE: very long window:
        # 10:36 payroll.docx opened, agent K3G1U8DN checks in (initial C2)
        # 10:46 psinject pivot to sports.com:443 C2, agent 4BW2MKUF
        # 10:51 kill initial agent K3G1U8DN
        # 11:03-11:13 DeathStar automated enumeration
        # 11:20 elevated agent on DC1 (VUBW3KYE)
        # 11:23-11:26 multiple UAC bypass attempts — FAILED
        # 11:33 DC1 pivots back: elevated agent 6H8SZPCW on 0501
        # 11:34 WMI subscription persistence
        # 11:35 kill agents 4BW2MKUF and 9HUGDCRL
        # 11:37-11:41 collection/enumeration (trusted docs, winenum, privesc check)
        # 11:45 upload plink.exe
        # 13:05 verify plink upload
        # 13:11 reverse SSH -> lost PSE agent 6H8SZPCW
        # 13:19 RDP into host via forwarded port (sysadmin account)
        # 13:26 download nc.exe as fileTransfer1000.exe from news.com:8080
        # 13:31 compress C:\documents -> export.zip
        # 13:44 exfil export.zip via nc to news.com:9999
        # 13:45 cleanup: delete fileTransfer1000.exe and export.zip
        # 13:46 RDP to Sysclient0974 (outbound pivot)
        # 15:28 close RDP session
    },
}


optc_sysclient0974 = {
    ("2019-09-24 13:46:58", "2019-09-24 15:27:32"): {
        "descrpt": "RDP pivot: file browsing, onward RDP to 0005",
        "report_sec": "Day 2",
        "tactics": [
            "Lateral Movement", # arrived via RDP from 0501; RDPed onward to 0005
            "Discovery", # browsed files in C:\documents at 13:51
            "Collection", # browsed files (viewing/assessment, no exfil from this host)
            "Command and Control", # RDP session (tunneled through plink SSH from 0501)
        ],
    },
}

optc_sysclient0051 = {
    ("2019-09-25 10:29:42", "2019-09-25 14:24:03"): {
        "descrpt": "Supply chain: malicious Notepad++ update, meterpreter, mimikatz, persistence, timestomp, RDP",
        "report_sec": "Day 3",
        "tactics": [
            "Initial Access", # supply chain: Notepad++ update downloaded malicious update.exe from notepadplus-sourceforge.net
            "Execution", # meterpreter reverse TCP payload (PID 2712 cKfGW.exe -> 53.192.68.50:8080)
            "Privilege Escalation", # getsystem (named pipe impersonation in memory) -> SYSTEM
            "Discovery", # cmd shell: local system info; ARP scan 142.20.56.0/22; enum_domain (DC); enum_shares
            "Credential Access", # mimikatz cleartext passwords and hashes at 10:44
            "Defense Evasion", # process migration: PID 2712 -> lsass PID 568; timestomp MAC times in C:\Windows\TEMP
            "Persistence", # autorun registry: HKLM\...\Run\RTqWaEHv; VBS script C:\Windows\TEMP\myHbYXTpViwX.vbx
            "Collection", # enum_applications (installed software inventory)
            "Command and Control", # meterpreter -> 53.192.68.50:8080; RDP at 13:42
        ],
    },
}

# # ABANDONED / TOO SHORT: 
# optc_sysclient0351 = {
#     ("2019-09-25 11:23:31", "2019-09-25 11:24:30"): {
#         "descrpt": "Supply chain: malicious Notepad++ update, meterpreter, migrate to lwabeat",
#         "report_sec": "Day 3",
#         "tactics": [
#             "Initial Access", # supply chain: Notepad++ update -> update.exe (meterpreter) from notepadplus-sourceforge.net
#             "Execution", # meterpreter payload f.exe (PID 1932) -> 53.192.68.50:8080
#             "Defense Evasion", # process migration: PID 1932 -> PID 1256 lwabeat (legitimate monitoring process)
#             "Command and Control", # meterpreter -> 53.192.68.50:8080
#         ],
#     },
# }
# optc_sysclient0811 = {
#     ("2019-09-24 10:40:14", "2019-09-24 13:25:46"): {
#         "descrpt": "Phishing target: macro-less Word doc, agent beacons then lost",
#         "report_sec": "Day 2",
#         "tactics": [
#             "Initial Access", # phishing email with payroll.docx from sgerard@ameblo.jp
#             "Execution", # PowerShell Empire agent DS8V3RNH (PID 3780) checks in
#             "Command and Control", # agent DS8V3RNH -> initial C2 (news.com:80 implied, or direct)
#         ],
#     },
# }
# optc_sysclient0402 = {
#     ("2019-09-23 13:25:41", "2019-09-23 14:06:01"): {
#         "descrpt": "Pivot host: WMI arrival, ping sweep, pivot out to 0660",
#         "report_sec": "Day 1",
#         "tactics": [
#             "Lateral Movement", # arrived via invoke_wmi from 0201; pivoted out to 0660 via invoke_wmi
#             "Execution", # PowerShell Empire agent NEK5H8GX (PID 3168)
#             "Discovery", # imported and ran ping sweep script against 142.20.57.0/24
#             "Command and Control", # agent NEK5H8GX -> news.com:80
#         ],
#     },
# }

# # NOT PART OF CURRENT SCOPE: 
# optc_sysclient0660 = {
#     ("2019-09-23 13:35:22", "2019-09-23 14:06:01"): {
#         "descrpt": "Pivot host: WMI arrival, mimikatz, DC enumeration, "
#                    "file download, pivot to DC1",
#         "report_sec": "Day 1",
#         "tactics": [
#             "Lateral Movement", # arrived via invoke_wmi from 0402; pivoted to DC1 via invoke_wmi
#             "Execution", # PowerShell Empire agent DS29HY41 (PID 880)
#             "Discovery", # ipconfig; ps (process listing); scripts for DC info; find domain controllers
#             "Credential Access", # mimikatz cleartext passwords from memory
#             "Defense Evasion", # psinject into user process — FAILED; shellcode inject into PID 4480 — FAILED
#             "Collection", # downloaded zipfldr.dll from C:\ at 14:02
#             "Command and Control", # agent DS29HY41 -> news.com:80
#         ],
#     },
# }
# optc_sysclient0005 = {
#     ("2019-09-24 13:54:43", "2019-09-24 15:23:26"): {
#         "descrpt": "RDP pivot endpoint: network share mount, large-scale data exfil",
#         "report_sec": "Day 2",
#         "tactics": [
#             "Lateral Movement", # arrived via RDP from 0974
#             "Discovery", # mounted network share \\142.20.61.135\share (implies knowledge of target)
#             "Collection", # compressed majority of share drive files -> allgone.zip; moved to Downloads
#             "Exfiltration", # 3.5 GB allgone.zip exfiled via nc (movingonup.exe) to news.com (port not stated, implied)
#             "Defense Evasion", # cleaned up files in Downloads folder after exfil
#             "Command and Control", # RDP session; nc.exe downloaded from news.com:4445
#         ],
#     },
# }