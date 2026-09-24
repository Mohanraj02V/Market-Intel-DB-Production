import React, { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, Clock, ExternalLink } from "lucide-react";
import api from "../services/api";

const HOUR_HEIGHT = 80;
const START_HOUR = 7;
const END_HOUR = 23;

export default function LqCalendarPage() {
  const [events, setEvents] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [nowMinute, setNowMinute] = useState(0);
  const scrollRef = useRef(null);

  useEffect(() => { fetchEvents(); }, [currentDate]);

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const mins = (now.getHours() - START_HOUR) * 60 + now.getMinutes();
      setNowMinute(mins);
    };
    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!loading && scrollRef.current) {
      const now = new Date();
      const scrollTo = Math.max(0, (now.getHours() - START_HOUR - 1)) * HOUR_HEIGHT;
      scrollRef.current.scrollTop = scrollTo;
    }
  }, [loading]);

  const fetchEvents = async () => {
    setLoading(true);
    try {
      const [meetingsRes, remindersRes] = await Promise.all([
        api.get("/meetings/"),
        api.get("/reminders/pending/")
      ]);
      const mData = meetingsRes.data.results || meetingsRes.data || [];
      const rData = remindersRes.data.results || remindersRes.data || [];

      const mappedMeetings = mData.map(m => ({ ...m, eventType: 'meeting' }));
      const mappedReminders = rData.map(r => ({ ...r, eventType: 'callback' }));
      setEvents([...mappedMeetings, ...mappedReminders]);
    } catch (err) {
      console.error("API ERROR:", err);
    }
    setLoading(false);
  };

  const getWeekDays = (date) => {
    const d = new Date(date);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    const monday = new Date(d.setDate(diff));
    return Array.from({ length: 7 }, (_, i) => {
      const next = new Date(monday);
      next.setDate(monday.getDate() + i);
      return next;
    });
  };

  const weekDays = getWeekDays(currentDate);
  const hours = Array.from({ length: END_HOUR - START_HOUR }, (_, i) => START_HOUR + i);

  const prevWeek = () => { const d = new Date(currentDate); d.setDate(d.getDate() - 7); setCurrentDate(d); };
  const nextWeek = () => { const d = new Date(currentDate); d.setDate(d.getDate() + 7); setCurrentDate(d); };

  const goToday = () => {
    setCurrentDate(new Date());
    setTimeout(() => {
      if (scrollRef.current) {
        const now = new Date();
        const scrollTo = Math.max(0, (now.getHours() - START_HOUR - 1)) * HOUR_HEIGHT;
        scrollRef.current.scrollTop = scrollTo;
      }
    }, 50);
  };

  const isSameDay = (d1, d2) =>
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate();

  const isToday = (d) => isSameDay(d, new Date());

  const getEventsForSlot = (day, hour) =>
    events.filter(e => {
      const eDate = new Date(e.scheduled_datetime);
      return isSameDay(eDate, day) && eDate.getHours() === hour;
    });

  const isCurrentWeek = weekDays.some(d => isToday(d));
  const nowLineTop = (nowMinute > 0 && nowMinute < (END_HOUR - START_HOUR) * 60)
    ? (nowMinute / 60) * HOUR_HEIGHT : null;

  const formatHour = (h) => {
    if (h === 0) return "12 AM";
    if (h === 12) return "12 PM";
    return h > 12 ? `${h - 12} PM` : `${h} AM`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#f8fafc", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ background: "#fff", borderBottom: "1px solid #e2e8f0", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ padding: 8, background: "#eef2ff", borderRadius: 12, color: "#4f46e5" }}>
            <CalendarIcon size={20} />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: "#0f172a" }}>Meeting Calendar</h1>
            <p style={{ margin: 0, fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>
              {events.length} scheduled event{events.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button onClick={goToday} style={{ padding: "8px 16px", fontSize: 13, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", borderRadius: 10, cursor: "pointer" }}>
            Today
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 4, background: "#f1f5f9", borderRadius: 10, padding: 4 }}>
            <button onClick={prevWeek} style={{ padding: 6, color: "#64748b", background: "none", border: "none", cursor: "pointer", borderRadius: 6, display: "flex" }}>
              <ChevronLeft size={20} />
            </button>
            <span style={{ fontSize: 13, fontWeight: 700, color: "#334155", padding: "0 12px", minWidth: 140, textAlign: "center" }}>
              {weekDays[0].toLocaleDateString("default", { month: "short", day: "numeric" })} – {weekDays[6].toLocaleDateString("default", { month: "short", day: "numeric", year: "numeric" })}
            </span>
            <button onClick={nextWeek} style={{ padding: 6, color: "#64748b", background: "none", border: "none", cursor: "pointer", borderRadius: 6, display: "flex" }}>
              <ChevronRight size={20} />
            </button>
          </div>
        </div>
      </div>

      {/* Day headers */}
      <div style={{ background: "#fff", borderBottom: "1px solid #e2e8f0", flexShrink: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "72px repeat(7, 1fr)", minWidth: "100%" }}>
          <div style={{ borderRight: "1px solid #f1f5f9" }} />
          {weekDays.map((day, i) => (
            <div key={i} style={{ padding: "10px 8px", borderRight: "1px solid #f1f5f9", textAlign: "center", background: isToday(day) ? "#eef2ff" : "transparent" }}>
              <div style={{ fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4, color: isToday(day) ? "#6366f1" : "#94a3b8" }}>
                {day.toLocaleDateString("default", { weekday: "short" })}
              </div>
              <div style={{
                width: 36, height: 36, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "center",
                borderRadius: "50%", fontSize: 17, fontWeight: 900,
                background: isToday(day) ? "#4f46e5" : "transparent",
                color: isToday(day) ? "#fff" : "#1e293b",
                boxShadow: isToday(day) ? "0 4px 12px rgba(79,70,229,0.3)" : "none"
              }}>
                {day.getDate()}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scrollable time grid */}
      <div ref={scrollRef} style={{ flex: 1, overflow: "auto" }}>
        <div style={{ position: "relative", background: "#fff", minWidth: "100%" }}>
          {/* Current time line */}
          {isCurrentWeek && nowLineTop !== null && (
            <div style={{ position: "absolute", left: 0, right: 0, top: nowLineTop, zIndex: 20, display: "flex", alignItems: "center", pointerEvents: "none" }}>
              <div style={{ width: 72, display: "flex", justifyContent: "flex-end", paddingRight: 8 }}>
                <div style={{ width: 9, height: 9, borderRadius: "50%", background: "#ef4444", boxShadow: "0 0 6px rgba(239,68,68,0.6)" }} />
              </div>
              <div style={{ flex: 1, height: 1.5, background: "#ef4444", opacity: 0.7 }} />
            </div>
          )}

          {hours.map((hour) => (
            <div key={hour} style={{ display: "grid", gridTemplateColumns: "72px repeat(7, 1fr)", borderBottom: "1px solid #f1f5f9", minHeight: HOUR_HEIGHT }}>
              <div style={{ borderRight: "1px solid #f1f5f9", display: "flex", alignItems: "flex-start", justifyContent: "flex-end", padding: "8px 8px 0 0", background: "#f8fafc" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8" }}>{formatHour(hour)}</span>
              </div>
              {weekDays.map((day) => {
                const slotEvents = getEventsForSlot(day, hour);
                return (
                  <div key={`${day.getTime()}-${hour}`} style={{ borderRight: "1px solid #f1f5f9", padding: 4, background: isToday(day) ? "rgba(238,242,255,0.3)" : "transparent" }}>
                    {slotEvents.map(e => {
                      const isMeeting = e.eventType === 'meeting';
                      const bgGradient = isMeeting ? "linear-gradient(135deg, #4f46e5, #6366f1)" : "linear-gradient(135deg, #059669, #10b981)";
                      const hoverShadow = isMeeting ? "rgba(79,70,229,0.4)" : "rgba(16,185,129,0.4)";
                      const baseShadow = isMeeting ? "rgba(79,70,229,0.25)" : "rgba(16,185,129,0.25)";
                      const subTextColor = isMeeting ? "#c7d2fe" : "#a7f3d0";
                      
                      return (
                        <div key={`${e.eventType}-${e.id}`} style={{ background: bgGradient, borderRadius: 10, padding: "8px 10px", color: "#fff", marginBottom: 4, boxShadow: `0 2px 8px ${baseShadow}`, cursor: "pointer", transition: "transform 0.1s, box-shadow 0.1s" }}
                          onMouseEnter={ev => { ev.currentTarget.style.transform = "translateY(-1px)"; ev.currentTarget.style.boxShadow = `0 4px 12px ${hoverShadow}`; }}
                          onMouseLeave={ev => { ev.currentTarget.style.transform = ""; ev.currentTarget.style.boxShadow = `0 2px 8px ${baseShadow}`; }}
                        >
                          <div style={{ fontSize: 12, fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.company_name}</div>
                          {e.key_person_name && (
                            <div style={{ fontSize: 10, color: subTextColor, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 1 }}>{e.key_person_name}</div>
                          )}
                          <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
                            <Clock size={10} color={subTextColor} />
                            <span style={{ fontSize: 10, fontWeight: 600, color: subTextColor }}>
                              {new Date(e.scheduled_datetime).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </span>
                          </div>
                          {!isMeeting && e.description && (
                            <div style={{ fontSize: 9, color: subTextColor, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 4 }}>
                              Call Back: {e.description}
                            </div>
                          )}
                          {isMeeting && e.meeting_link && (
                            <a href={e.meeting_link} target="_blank" rel="noreferrer"
                              style={{ display: "inline-flex", alignItems: "center", gap: 3, marginTop: 5, fontSize: 10, fontWeight: 700, background: "rgba(255,255,255,0.2)", padding: "2px 6px", borderRadius: 4, color: "#fff", textDecoration: "none" }}
                              onClick={ev => ev.stopPropagation()}>
                              <ExternalLink size={10} /> Join
                            </a>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
