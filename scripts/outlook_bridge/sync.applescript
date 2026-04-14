-- sync.applescript
--
-- Queries Outlook for Mac for recent/upcoming calendar events and recent
-- Inbox messages. Writes newline-delimited JSON (one item per line) to
-- stdout — one record per event or message.
--
-- Each line has shape (calendar):
--   {"kind":"calendar","external_id":"...","subject":"...","start":"...","end":"...","location":"...","organizer":"...","attendees":[...],"body":"..."}
-- Or (mail):
--   {"kind":"mail","external_id":"...","subject":"...","sender":"...","to":[...],"cc":[...],"received_at":"...","body":"..."}
--
-- Error handling: any property access that fails (missing, permission
-- denied) is caught per-item — one broken row does not poison the batch.
-- Overall errors are written to stderr so the Python bridge can surface
-- them without parsing a malformed stdout.

on run argv
    set pastDays to 7
    set futureDays to 14
    set mailDays to 3
    set mailMax to 50

    set startDate to (current date) - (pastDays * days)
    set endDate to (current date) + (futureDays * days)
    set mailSince to (current date) - (mailDays * days)

    set outputLines to {}

    -- ── Calendar events ────────────────────────────────────────────────
    try
        tell application "Microsoft Outlook"
            set theEvents to (every calendar event whose start time ≥ startDate and start time ≤ endDate)
        end tell
        repeat with ev in theEvents
            try
                set evLine to my renderCalendar(ev)
                if evLine is not missing value then
                    set end of outputLines to evLine
                end if
            on error errMsg
                log "calendar item skipped: " & errMsg
            end try
        end repeat
    on error errMsg
        log "calendar query failed: " & errMsg
    end try

    -- ── Inbox messages ─────────────────────────────────────────────────
    try
        tell application "Microsoft Outlook"
            set inboxMsgs to (messages of inbox whose time received ≥ mailSince)
        end tell
        -- Cap to mailMax most recent (AppleScript lists are 1-indexed)
        set msgCount to count of inboxMsgs
        if msgCount > mailMax then
            set inboxMsgs to items (msgCount - mailMax + 1) thru msgCount of inboxMsgs
        end if
        repeat with msg in inboxMsgs
            try
                set msgLine to my renderMail(msg)
                if msgLine is not missing value then
                    set end of outputLines to msgLine
                end if
            on error errMsg
                log "mail item skipped: " & errMsg
            end try
        end repeat
    on error errMsg
        log "mail query failed: " & errMsg
    end try

    -- One NDJSON line per item
    set AppleScript's text item delimiters to linefeed
    return (outputLines as text)
end run


-- ─── Renderers ──────────────────────────────────────────────────────────

on renderCalendar(ev)
    tell application "Microsoft Outlook"
        try
            set evId to (id of ev) as text
        on error
            return missing value
        end try
        try
            set evSubject to (subject of ev) as text
        on error
            set evSubject to ""
        end try
        try
            set evStart to (start time of ev) as text
        on error
            set evStart to ""
        end try
        try
            set evEnd to (end time of ev) as text
        on error
            set evEnd to ""
        end try
        try
            set evLocation to (location of ev) as text
        on error
            set evLocation to ""
        end try
        try
            set evBody to (content of ev) as text
            if (length of evBody) > 2000 then
                set evBody to text 1 thru 2000 of evBody
            end if
        on error
            set evBody to ""
        end try
        -- Organizer + attendees: try to grab emails; skip silently on failure
        set organizerEmail to ""
        try
            set organizerEmail to (email address of organizer of ev) as text
        end try
        set attendeeList to {}
        try
            set theAttendees to (every attendee of ev)
            repeat with a in theAttendees
                try
                    set end of attendeeList to (email address of a) as text
                end try
            end repeat
        end try
    end tell

    set jsonFields to {}
    set end of jsonFields to "\"kind\":\"calendar\""
    set end of jsonFields to "\"external_id\":" & my jsonString(evId)
    set end of jsonFields to "\"subject\":" & my jsonString(evSubject)
    set end of jsonFields to "\"start\":" & my jsonString(evStart)
    set end of jsonFields to "\"end\":" & my jsonString(evEnd)
    if evLocation is not "" then set end of jsonFields to "\"location\":" & my jsonString(evLocation)
    if organizerEmail is not "" then set end of jsonFields to "\"organizer\":" & my jsonString(organizerEmail)
    if (count of attendeeList) > 0 then set end of jsonFields to "\"attendees\":" & my jsonStringArray(attendeeList)
    if evBody is not "" then set end of jsonFields to "\"body\":" & my jsonString(evBody)

    set AppleScript's text item delimiters to ","
    return "{" & (jsonFields as text) & "}"
end renderCalendar


on renderMail(msg)
    tell application "Microsoft Outlook"
        try
            set msgId to (id of msg) as text
        on error
            return missing value
        end try
        try
            set msgSubject to (subject of msg) as text
        on error
            set msgSubject to ""
        end try
        try
            set msgReceived to (time received of msg) as text
        on error
            set msgReceived to ""
        end try
        set senderEmail to ""
        try
            set senderEmail to (email address of sender of msg) as text
        end try
        try
            set msgBody to (plain text content of msg) as text
        on error
            try
                set msgBody to (content of msg) as text
            on error
                set msgBody to ""
            end try
        end try
        if (length of msgBody) > 1500 then
            set msgBody to text 1 thru 1500 of msgBody
        end if
        set toList to {}
        try
            set toRecips to (every to recipient of msg)
            repeat with r in toRecips
                try
                    set end of toList to (email address of r) as text
                end try
            end repeat
        end try
        set ccList to {}
        try
            set ccRecips to (every cc recipient of msg)
            repeat with r in ccRecips
                try
                    set end of ccList to (email address of r) as text
                end try
            end repeat
        end try
    end tell

    set jsonFields to {}
    set end of jsonFields to "\"kind\":\"mail\""
    set end of jsonFields to "\"external_id\":" & my jsonString(msgId)
    set end of jsonFields to "\"subject\":" & my jsonString(msgSubject)
    if senderEmail is not "" then set end of jsonFields to "\"sender\":" & my jsonString(senderEmail)
    if (count of toList) > 0 then set end of jsonFields to "\"to\":" & my jsonStringArray(toList)
    if (count of ccList) > 0 then set end of jsonFields to "\"cc\":" & my jsonStringArray(ccList)
    if msgReceived is not "" then set end of jsonFields to "\"received_at\":" & my jsonString(msgReceived)
    if msgBody is not "" then set end of jsonFields to "\"body\":" & my jsonString(msgBody)

    set AppleScript's text item delimiters to ","
    return "{" & (jsonFields as text) & "}"
end renderMail


-- ─── JSON escaping ──────────────────────────────────────────────────────

on jsonString(s)
    -- Escape \ then " then CR, LF, TAB so the output is a valid JSON
    -- string literal. Any other control character gets passed through;
    -- in practice Outlook's text fields don't contain raw \x00-\x1F
    -- bytes other than CR/LF/TAB.
    set s to my replaceAll(s, "\\", "\\\\")
    set s to my replaceAll(s, "\"", "\\\"")
    set s to my replaceAll(s, return, "\\n")
    set s to my replaceAll(s, linefeed, "\\n")
    set s to my replaceAll(s, tab, "\\t")
    return "\"" & s & "\""
end jsonString


on jsonStringArray(lst)
    set escaped to {}
    repeat with v in lst
        set end of escaped to my jsonString(v as text)
    end repeat
    set AppleScript's text item delimiters to ","
    return "[" & (escaped as text) & "]"
end jsonStringArray


on replaceAll(s, findStr, replaceStr)
    set AppleScript's text item delimiters to findStr
    set parts to text items of s
    set AppleScript's text item delimiters to replaceStr
    set result to parts as text
    set AppleScript's text item delimiters to ""
    return result
end replaceAll
