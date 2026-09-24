export function localDateTimeToUTC(dateStr, timeStr, timeZone) {
    if (!timeZone) timeZone = 'UTC';
    
    let [year, month, day] = dateStr.split('-').map(Number);
    let [hour, minute] = timeStr.split(':').map(Number);
    
    let utcGuess = new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
    let currentUtc = utcGuess.getTime();
    
    for (let i = 0; i < 4; i++) {
        let parts;
        try {
            parts = new Intl.DateTimeFormat('en-US', {
                timeZone,
                year: 'numeric', month: 'numeric', day: 'numeric',
                hour: 'numeric', minute: 'numeric', second: 'numeric',
                hourCycle: 'h23'
            }).formatToParts(new Date(currentUtc));
        } catch (e) {
            // Fallback for invalid timezone
            return new Date(`${dateStr}T${timeStr}:00Z`).toISOString();
        }
        
        const p = {};
        parts.forEach(part => { p[part.type] = parseInt(part.value, 10); });
        if (p.hour === 24) p.hour = 0;
        
        const localInTZ = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
        const targetLocal = Date.UTC(year, month - 1, day, hour, minute, 0);
        
        const diff = targetLocal - localInTZ;
        if (diff === 0) break;
        currentUtc += diff;
    }
    
    return new Date(currentUtc).toISOString();
}

export function formatDateTimeForUser(utcString, timeZone) {
    if (!utcString) return '';
    if (!timeZone) timeZone = 'UTC';
    const d = new Date(utcString);
    try {
        return d.toLocaleString('en-US', {
            timeZone,
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) {
        return d.toLocaleString();
    }
}

export function formatTimeForUser(utcString, timeZone) {
    if (!utcString) return '';
    if (!timeZone) timeZone = 'UTC';
    const d = new Date(utcString);
    try {
        return d.toLocaleTimeString('en-US', {
            timeZone,
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) {
        return d.toLocaleTimeString();
    }
}

/**
 * Returns a naive Date object where local accessors (.getHours(), .getDate(), etc) 
 * will return the values of the given timezone. This allows existing grid 
 * calendars relying on local time to work correctly.
 */
export function getZonedDate(dateInput, timeZone) {
    if (!timeZone) timeZone = 'UTC';
    const d = dateInput ? new Date(dateInput) : new Date();
    try {
        const str = d.toLocaleString('en-US', { timeZone, hourCycle: 'h23' }); 
        // e.g. "9/24/2026, 13:28:38"
        return new Date(str);
    } catch (e) {
        return d;
    }
}
