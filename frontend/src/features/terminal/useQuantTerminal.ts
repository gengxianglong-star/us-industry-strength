import { useCallback, useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";
import type { IndustryRow, SnapshotPayload } from "../../lib/industry";
import {
  buildRotationNodes,
  filterAlphaRows,
  type AlphaFilter,
  type RotationNode,
} from "../../lib/rotationLogic";
import type { BreadthRow } from "./terminalRegime";

type BreadthPayload = {
  rows?: BreadthRow[];
  coverage?: { last_date?: string; row_count?: number };
};

export type { AlphaFilter, RotationNode };

export function useQuantTerminal() {
  const [breadth, setBreadth] = useState<BreadthPayload | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [breadthData, snap] = await Promise.all([
        fetchJson<BreadthPayload>("/api/breadth?limit=60"),
        fetchJson<SnapshotPayload>("/api/snapshots/latest"),
      ]);
      setBreadth(breadthData);
      setSnapshot(snap);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load terminal data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const industries: IndustryRow[] = snapshot?.industries || [];
  const ratio10 = +(breadth?.rows?.[0]?.c4_num ?? 1);
  const rotationNodes = buildRotationNodes(industries, ratio10);

  return {
    breadth,
    snapshot,
    loading,
    error,
    reload,
    industries,
    rotationNodes,
    ratio10,
    filterAlphaRows: (filter: AlphaFilter) => filterAlphaRows(rotationNodes, filter),
  };
}
