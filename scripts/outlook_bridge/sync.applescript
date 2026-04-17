-- sync.applescript
--
-- Reads from macOS native Mail + Calendar apps. Emits NDJSON on stdout.
--
-- CRASH-SAFE CONSTRAINTS (learned the hard way on a 4-account Mail setup):
--
--   * NEVER query `inbox` (the unified smart mailbox). It evaluates the
--     `whose` clause across every account, forcing metadata rehydration
--     of tens of thousands of messages — Mail.app balloons to multi-GB
--     and the machine swap-thrashes. We enumerate each account's own
--     Inbox mailbox separately and cap per account.
--
--   * NEVER request `content of msg`. Pulling bodies forces Mail to
--     decode MIME + inline images for every filtered message; a handful
--     of HTML newsletters can blow RAM by hundreds of MB. We send only
--     subject / sender / date — the classifier works fine on that.
--
--   * NEVER wrap the tell blocks in `with timeout`. When an AppleEvent
--     is interrupted by the timeout, subsequent property reads on the
--     same reference silently return empty strings. The hang-safety is
--     enforced at a higher layer: bridge.py runs osascript with
--     OSASCRIPT_TIMEOUT_SEC and SIGKILLs the whole process if needed.
--
--   * Iterate `repeat with i from 1 to n` + `item i of list`, not
--     `repeat with x in list`. The latter strips application context
--     for references that came out of a `whose`-filtered query.
--
--   * Do all JSON rendering AFTER the tell block exits. Calling `my
--     handler(...)` from inside a tell block and passing string args
--     corrupts the args — the handler sees empty strings. So each
--     branch collects raw tuples (a list of string lists), and the tail
--     of the run handler maps them to JSON using the local helpers.

on run argv
    set pastDays to 7
    set futureDays to 14
    set mailDays to 3
    set mailPerAccountMax to 25    -- hard cap per mail account
    set eventsPerCalendarMax to 50 -- hard cap per calendar

    set startDate to (current date) - (pastDays * days)
    set endDate to (current date) + (futureDays * days)
    set mailSince to (current date) - (mailDays * days)

    -- Raw tuples: each entry is a list of strings in a fixed positional
    -- schema, handled by the renderer below. Keeping these plain strings
    -- (not records or refs) means they survive the tell → script-context
    -- boundary without losing content.
    set calendarRows to {}   -- {uid, subject, startISO, endISO, location}
    set mailRows to {}       -- {id, subject, receivedISO, sender, account}

    -- ── Calendar events (Apple Calendar) ───────────────────────────────
    try
        tell application "Calendar"
            set allCalendars to every calendar
            repeat with cal in allCalendars
                try
                    set calName to name of cal
                on error
                    set calName to "(unknown)"
                end try
                try
                    set calEvents to (every event of cal whose start date is greater than or equal to startDate and start date is less than or equal to endDate)
                    set evCount to count of calEvents
                    if evCount > eventsPerCalendarMax then
                        log "calendar '" & calName & "' skipped: " & evCount & " events in window (> cap)"
                    else
                        repeat with i from 1 to evCount
                            try
                                set ev to item i of calEvents
                                set evUid to ""
                                try
                                    set evUid to (uid of ev) as text
                                end try
                                set evSubject to ""
                                try
                                    set evSubject to (summary of ev) as text
                                end try
                                if evUid is not "" and evSubject is not "" then
                                    set evStart to ""
                                    try
                                        set evStart to (start date of ev) as text
                                    end try
                                    set evEnd to ""
                                    try
                                        set evEnd to (end date of ev) as text
                                    end try
                                    set evLocation to ""
                                    try
                                        set evLocation to (location of ev) as text
                                    end try
                                    -- Skipping `description of ev` by
                                    -- design — meeting invite bodies
                                    -- are HTML blobs and reading them
                                    -- per event was making runs time out.
                                    set end of calendarRows to {evUid, evSubject, evStart, evEnd, evLocation}
                                end if
                            on error errMsg
                                log "event skipped: " & errMsg
                            end try
                        end repeat
                    end if
                on error errMsg
                    log "calendar '" & calName & "' query skipped: " & errMsg
                end try
            end repeat
        end tell
    on error errMsg
        log "calendar block failed: " & errMsg
    end try

    -- ── Inbox messages (Apple Mail, per-account) ──────────────────────
    try
        tell application "Mail"
            set allAccounts to every account
            repeat with acct in allAccounts
                try
                    set acctName to name of acct
                on error
                    set acctName to "(unknown)"
                end try
                try
                    -- Apple Mail's inbox name varies by account type:
                    --   IMAP (iCloud)     → "INBOX" (all caps)
                    --   Exchange/EWS      → "Inbox" (title case)
                    --   some custom POP   → "inbox"
                    -- We try each. Falling back to `first mailbox` is
                    -- actively harmful: for Exchange accounts the first
                    -- mailbox is usually "Conversation History", which
                    -- is near-empty and not the inbox the user means.
                    set inboxMbox to missing value
                    try
                        set inboxMbox to mailbox "INBOX" of acct
                    on error
                        try
                            set inboxMbox to mailbox "Inbox" of acct
                        on error
                            try
                                set inboxMbox to mailbox "inbox" of acct
                            end try
                        end try
                    end try
                    if inboxMbox is missing value then
                        log "account '" & acctName & "' has no identifiable inbox mailbox — skipped"
                    else
                        set acctMsgs to (messages of inboxMbox whose date received is greater than or equal to mailSince)
                        set msgCount to count of acctMsgs
                        set startIdx to 1
                        if msgCount > mailPerAccountMax then
                            set startIdx to msgCount - mailPerAccountMax + 1
                        end if
                        repeat with i from startIdx to msgCount
                            try
                                set msg to item i of acctMsgs
                                set msgId to ""
                                try
                                    set msgId to (id of msg) as text
                                end try
                                if msgId is not "" then
                                    set msgSubject to ""
                                    try
                                        set msgSubject to (subject of msg) as text
                                    end try
                                    set msgReceived to ""
                                    try
                                        set msgReceived to (date received of msg) as text
                                    end try
                                    set senderText to ""
                                    try
                                        set senderText to (sender of msg) as text
                                    end try
                                    -- Deliberately NOT reading `content of msg`.
                                    set end of mailRows to {msgId, msgSubject, msgReceived, senderText, acctName}
                                end if
                            on error errMsg
                                log "mail item skipped: " & errMsg
                            end try
                        end repeat
                    end if
                on error errMsg
                    log "mail account '" & acctName & "' skipped: " & errMsg
                end try
            end repeat
        end tell
    on error errMsg
        log "mail block failed: " & errMsg
    end try

    -- ── Render NDJSON (outside any tell block) ────────────────────────
    -- Use indexed iteration, not `repeat with row in list`. The latter
    -- binds `row` as an ITEM REFERENCE; when we pass that ref to a
    -- handler, `item 1 of row` inside the handler can't resolve it and
    -- returns empty strings. Hard-won lesson.
    set outputLines to {}
    repeat with i from 1 to count of calendarRows
        set end of outputLines to my renderCalendarRow(item i of calendarRows)
    end repeat
    repeat with i from 1 to count of mailRows
        set end of outputLines to my renderMailRow(item i of mailRows)
    end repeat
    set AppleScript's text item delimiters to linefeed
    return (outputLines as text)
end run


-- ─── Renderers ──────────────────────────────────────────────────────────
-- Each expects a list of plain strings in the order shown above. Running
-- after the tell blocks have exited means `my ...` handler calls don't
-- go through the app bridge and string args arrive intact.

on renderCalendarRow(row)
    set evUid to item 1 of row
    set evSubject to item 2 of row
    set evStart to item 3 of row
    set evEnd to item 4 of row
    set evLocation to item 5 of row
    set jsonFields to {}
    set end of jsonFields to "\"kind\":\"calendar\""
    set end of jsonFields to "\"external_id\":" & my jsonString(evUid)
    set end of jsonFields to "\"subject\":" & my jsonString(evSubject)
    set end of jsonFields to "\"start\":" & my jsonString(evStart)
    set end of jsonFields to "\"end\":" & my jsonString(evEnd)
    if evLocation is not "" then set end of jsonFields to "\"location\":" & my jsonString(evLocation)
    set AppleScript's text item delimiters to ","
    return "{" & (jsonFields as text) & "}"
end renderCalendarRow


on renderMailRow(row)
    set msgId to item 1 of row
    set msgSubject to item 2 of row
    set msgReceived to item 3 of row
    set senderText to item 4 of row
    set acctName to item 5 of row
    set jsonFields to {}
    set end of jsonFields to "\"kind\":\"mail\""
    set end of jsonFields to "\"external_id\":" & my jsonString(msgId)
    set end of jsonFields to "\"subject\":" & my jsonString(msgSubject)
    if senderText is not "" then set end of jsonFields to "\"sender\":" & my jsonString(senderText)
    if msgReceived is not "" then set end of jsonFields to "\"received_at\":" & my jsonString(msgReceived)
    if acctName is not "" then set end of jsonFields to "\"account\":" & my jsonString(acctName)
    set AppleScript's text item delimiters to ","
    return "{" & (jsonFields as text) & "}"
end renderMailRow


on jsonString(s)
    set s to my replaceAll(s, "\\", "\\\\")
    set s to my replaceAll(s, "\"", "\\\"")
    set s to my replaceAll(s, return, "\\n")
    set s to my replaceAll(s, linefeed, "\\n")
    set s to my replaceAll(s, tab, "\\t")
    return "\"" & s & "\""
end jsonString


on replaceAll(s, findStr, replaceStr)
    set AppleScript's text item delimiters to findStr
    set parts to text items of s
    set AppleScript's text item delimiters to replaceStr
    -- AppleScript gotcha: `parts as text` is a LAZY coercion bound to
    -- the current text-item-delimiter state. If we reset delimiters
    -- before returning, the caller's read re-evaluates against the
    -- new (empty) delimiter and gets back an empty string. Force a
    -- concrete value via concatenation before the reset.
    set concrete to "" & (parts as text)
    set AppleScript's text item delimiters to ""
    return concrete
end replaceAll
