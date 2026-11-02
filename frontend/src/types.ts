/** The parts of Home Assistant's `hass` object the panel uses. */
export interface HomeAssistant {
  language: string;
  themes?: { darkMode?: boolean };
  user?: { is_admin: boolean };
  config: { unit_system: { length: string } };
  connection: {
    sendMessagePromise<T>(message: Record<string, unknown>): Promise<T>;
  };
}

export interface Spot {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  /** Meters. */
  radius: number;
  water_type: string;
  offshore: string[];
  exposed: string[];
}

export interface Boat {
  id: string;
  name: string;
  size_class: string;
  /** Meters. */
  length: number;
}

export interface Sailor {
  id: string;
  name: string;
  skill: string;
  /** Boat IDs, the usual boat first. */
  boats: string[];
  days: string[];
  start: string | null;
  end: string | null;
}

/** The reply to `sailcast/config`. */
export interface SailCastConfig {
  spots: Spot[];
  boats: Boat[];
  sailors: Sailor[];
}
