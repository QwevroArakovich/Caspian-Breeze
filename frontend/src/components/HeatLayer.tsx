import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.heat";
import type { HeatPoint } from "../api";

export default function HeatLayer({ points }: { points: HeatPoint[] }) {
  const map = useMap();
  useEffect(() => {
    const layer = L.heatLayer(points, {
      radius: 30,
      blur: 22,
      minOpacity: 0.35,
      maxZoom: 15,
      gradient: { 0.3: "#F7D774", 0.6: "#EE8A2F", 1: "#B3342A" },
    }).addTo(map);
    return () => {
      map.removeLayer(layer);
    };
  }, [map, points]);
  return null;
}
