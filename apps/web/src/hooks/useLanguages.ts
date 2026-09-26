import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { LanguageCapability } from "../lib/types";

export function useLanguages() {
  return useQuery({
    queryKey: ["languages"],
    queryFn: () => api<LanguageCapability[]>("/api/v1/languages"),
    staleTime: 5 * 60_000,
  });
}

export function languageLabel(caps: LanguageCapability[] | undefined, code: string): string {
  const found = caps?.find((c) => c.code === code);
  return found ? `${found.name}${found.native_name && found.native_name !== found.name ? ` · ${found.native_name}` : ""}` : code.toUpperCase();
}

export function statusTone(status: string): "good" | "warn" | "bad" | "neutral" {
  switch (status) {
    case "PRODUCTION":
    case "SUPPORTED":
      return "good";
    case "BETA":
      return "warn";
    default:
      return "neutral";
  }
}
