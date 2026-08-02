import axios from "axios";

import type {
  Itinerary,
  TripEditPayload,
  TripListResponse,
  TripRequestPayload,
  WeatherForecastResponse,
} from "../types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5分钟超时，行程生成涉及 RAG+LLM+地图多个步骤，耗时较长
});

// ── 行程生成 ──────────────────────────────────

export async function generateTrip(payload: TripRequestPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/api/trips/generate", payload);
  return response.data;
}

export async function editTrip(payload: TripEditPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/api/trips/edit", payload);
  return response.data;
}

// ── 行程保存与查询 ──────────────────────────────

// 后端 POST /save 直接返回 Itinerary（response_model=Itinerary）
export async function saveTrip(itinerary: Itinerary): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/api/trips/save", {
    trip_id: itinerary.trip_id,
    itinerary,
    user_id: "frontend_demo_user",
  });
  return response.data;
}

export async function listTrips(): Promise<TripListResponse> {
  const response = await api.get<TripListResponse>("/api/trips/");
  return response.data;
}

// 后端 GET /{trip_id} 直接返回 Itinerary（response_model=Itinerary）
export async function getTripDetail(tripId: string): Promise<Itinerary> {
  const response = await api.get<Itinerary>(`/api/trips/${tripId}`);
  return response.data;
}

export async function deleteTrip(tripId: string): Promise<void> {
  await api.delete(`/api/trips/${tripId}`);
}

// ── 天气查询 ──────────────────────────────────

export async function fetchWeatherForecast(city: string): Promise<WeatherForecastResponse> {
  const response = await api.get<WeatherForecastResponse>("/api/weather/forecast", {
    params: { city },
  });
  return response.data;
}

// ── 文档导出 ──────────────────────────────────

export function getMarkdownExportUrl(tripId: string): string {
  return `${API_BASE_URL}/api/export/${encodeURIComponent(tripId)}/markdown`;
}

export function getPdfExportUrl(tripId: string): string {
  return `${API_BASE_URL}/api/export/${encodeURIComponent(tripId)}/pdf`;
}

export default api;
