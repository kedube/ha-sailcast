/** The panel's WebSocket commands, typed. */
import type {
  AutoCalendar,
  Bounds,
  Briefing,
  Connection,
  DayHours,
  Forecast,
  PlannedList,
  PlannedSail,
  Preferences,
  Sailor,
  SailCastConfig,
  SaveResult,
  Shoreline,
  SourceSuggestions,
  WindGrid,
  WindView,
} from "./types";

export type ProfileKind = "spot" | "boat" | "sailor";

export class Api {
  constructor(private readonly connection: Connection) {}

  private send<T>(type: string, values: Record<string, unknown> = {}): Promise<T> {
    return this.connection.sendMessagePromise<T>({ type: `sailcast/${type}`, ...values });
  }

  config(): Promise<SailCastConfig> {
    return this.send("config");
  }

  /** A sailor's week at a spot in one of their boats. */
  forecast(spot: string, sailor: string, boat: string | undefined): Promise<Forecast> {
    return this.send("forecast", boat ? { spot, sailor, boat } : { spot, sailor });
  }

  /**
   * A sailor's AI briefing in `language`, or null if none was written. With
   * `write`, the AI writes one if the kept one isn't current.
   */
  briefing(sailor: string, language: string, write: boolean): Promise<Briefing | null> {
    return this.send("briefing", { sailor, language, write });
  }

  /** Call back whenever results, planned sails or settings change. */
  subscribe(callback: () => void): Promise<() => Promise<void>> {
    return this.connection.subscribeMessage(callback, { type: "sailcast/subscribe" });
  }

  preferences(): Promise<Preferences> {
    return this.send("preferences/get");
  }

  setPreferences(changes: Partial<Record<keyof Preferences, string | null>>): Promise<Preferences> {
    return this.send("preferences/set", changes);
  }

  save(
    kind: ProfileKind,
    name: string,
    data: Record<string, unknown>,
    profile?: string,
  ): Promise<SaveResult> {
    return this.send(
      "settings/save",
      profile ? { kind, name, data, profile } : { kind, name, data },
    );
  }

  remove(kind: ProfileKind, profile: string): Promise<SaveResult> {
    return this.send("settings/delete", { kind, profile });
  }

  sources(latitude: number, longitude: number): Promise<SourceSuggestions> {
    return this.send("settings/sources", { latitude, longitude });
  }

  /** How far open water reaches from a pin; the first time takes a few seconds. */
  shoreline(latitude: number, longitude: number): Promise<Shoreline> {
    return this.send("settings/shoreline", { latitude, longitude });
  }

  addToCalendar(sail: {
    spot: string;
    sailor: string;
    boat: string;
    calendar: string;
    start: string;
    end: string;
    title: string;
    watch: boolean;
    /** The language for the event's description. */
    language: string;
  }): Promise<PlannedSail> {
    return this.send("calendar/add", sail);
  }

  removeFromCalendar(planned: string): Promise<{ deleted: boolean }> {
    return this.send("calendar/remove", { planned });
  }

  windGrid(spot: string): Promise<WindGrid> {
    return this.send("wind_grid", { spot });
  }

  /** The wind over what the map shows, unless the grid it has (`have`) still serves. */
  windView(view: Bounds, have?: string): Promise<WindView> {
    return this.send("wind_view", { ...view, ...(have ? { have } : {}) });
  }

  planned(): Promise<PlannedList> {
    return this.send("planned/list");
  }

  setSkipped(sailor: string, days: string[]): Promise<string[]> {
    return this.send("planned/skipped", { sailor, days });
  }

  /**
   * Set a sailor's hours for one date: "off" for not sailing, hours without
   * times for the whole day, or "usual" to go back to the weekday's hours.
   */
  setHours(
    sailor: string,
    date: string,
    hours: DayHours | "off" | "usual",
  ): Promise<{ date: string; errors?: Record<string, string> }> {
    return this.send("hours", { sailor, date, hours });
  }

  /** Save a sailor's automatic adding, keeping the rest of their profile. */
  saveAutoCalendar(sailor: Sailor, auto: AutoCalendar | null): Promise<SaveResult> {
    const { id, name, week, ...data } = sailor;
    return this.save("sailor", name, { ...data, hours: week, auto_calendar: auto }, id);
  }
}
