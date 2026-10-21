import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchCampaigns, fetchContacts } from "../contacts";
import type { ItemsEnvelope } from "../types";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../api", () => ({ api: apiMock }));

describe("contacts client", () => {
  beforeEach(() => apiMock.mockReset());

  it("reads the paginated envelope the API returns", async () => {
    // The endpoint answers with `{ items: [...], total }` — a bare-array read
    // would silently produce an empty list (issue #109 class 1).
    const body: ItemsEnvelope<{ id: string; display_name: string }> = {
      items: [{ id: "c1", display_name: "Ada" }],
      total: 1,
    };
    apiMock.mockResolvedValue(body);

    const contacts = await fetchContacts();
    expect(contacts).toHaveLength(1);
    expect(contacts[0].display_name).toBe("Ada");
  });

  it("survives a response without items", async () => {
    apiMock.mockResolvedValue({});
    expect(await fetchContacts()).toEqual([]);
    expect(await fetchCampaigns()).toEqual([]);
  });
});
