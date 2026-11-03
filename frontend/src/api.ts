/** The panel's WebSocket commands, typed. */
import type {
  AutoCalendar,
  Connection,
  Forecast,
  PlannedList,
  PlannedSail,
  Preferences,
  SailCastConfig,
  SaveResult,
  Shoreline,
  SourceSuggestions,
  WindGrid,
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

  forecast(spot: string, sailor: string, boat?: string): Promise<Forecast> {
    return this.send("forecast", boat ? { spot, sailor, boat } : { spot, sailor });
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
  }): Promise<PlannedSail> {
    return this.send("calendar/add", sail);
  }

  removeFromCalendar(planned: string): Promise<{ deleted: boolean }> {
    return this.send("calendar/remove", { planned });
  }

  windGrid(spot: string): Promise<WindGrid> {
    return this.send("wind_grid", { spot });
  }

  planned(): Promise<PlannedList> {
    return this.send("planned/list");
  }

  setSkipped(sailor: string, days: string[]): Promise<string[]> {
    return this.send("planned/skipped", { sailor, days });
  }

  /** Save a sailor's automatic adding, keeping the rest of their profile. */
  saveAutoCalendar(
    sailor: { id: string; name: string } & Record<string, unknown>,
    auto: AutoCalendar | null,
  ): Promise<SaveResult> {
    const { id, name, ...data } = sailor;
    return this.save("sailor", name, { ...data, auto_calendar: auto }, id);
  }
}
