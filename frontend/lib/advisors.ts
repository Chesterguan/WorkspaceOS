export interface AdvisorInfo {
  id: string;
  name: string;
  tagline: string;
  expertise: string[];
  color: string;
  avatar: string;
}

export const ADVISORS: Record<string, AdvisorInfo> = {
  yc_partner: {
    id: "yc_partner",
    name: "YC Partner",
    tagline: "Startup Strategy & PMF",
    expertise: ["startup", "pmf", "fundraising", "metrics", "pitch"],
    color: "#F59E0B",
    avatar: "/avatars/yc_partner.svg",
  },
  elon_musk: {
    id: "elon_musk",
    name: "Elon Musk",
    tagline: "First Principles & Moonshots",
    expertise: ["scaling", "engineering", "vision", "first-principles", "moonshot"],
    color: "#3B82F6",
    avatar: "/avatars/elon_musk.svg",
  },
  alex_hormozi: {
    id: "alex_hormozi",
    name: "Alex Hormozi",
    tagline: "$100M Offers & Value",
    expertise: ["pricing", "monetization", "offers", "leads", "sales"],
    color: "#10B981",
    avatar: "/avatars/alex_hormozi.svg",
  },
  greg_isenberg: {
    id: "greg_isenberg",
    name: "Greg Isenberg",
    tagline: "Community-Led Growth",
    expertise: ["community", "social", "audience", "virality", "retention"],
    color: "#8B5CF6",
    avatar: "/avatars/greg_isenberg.svg",
  },
  nathan_gotch: {
    id: "nathan_gotch",
    name: "Nathan Gotch",
    tagline: "SEO & Organic Growth",
    expertise: ["seo", "traffic", "organic-growth", "keywords", "content-marketing"],
    color: "#EC4899",
    avatar: "/avatars/nathan_gotch.svg",
  },
  julia_mccoy: {
    id: "julia_mccoy",
    name: "Julia McCoy",
    tagline: "AI Content Strategy",
    expertise: ["content", "branding", "ai-content", "writing", "marketing"],
    color: "#F97316",
    avatar: "/avatars/julia_mccoy.svg",
  },
  growth_tribe: {
    id: "growth_tribe",
    name: "Growth Tribe",
    tagline: "Growth Hacking & Experiments",
    expertise: ["growth-hacking", "experiments", "analytics", "activation", "retention"],
    color: "#06B6D4",
    avatar: "/avatars/growth_tribe.svg",
  },
  dan_koe: {
    id: "dan_koe",
    name: "Dan Koe",
    tagline: "One-Person Business",
    expertise: ["solopreneur", "leverage", "digital-products", "personal-brand", "focus"],
    color: "#EF4444",
    avatar: "/avatars/dan_koe.svg",
  },
};

export const ADVISOR_ORDER = [
  "yc_partner", "elon_musk", "alex_hormozi", "greg_isenberg",
  "nathan_gotch", "julia_mccoy", "growth_tribe", "dan_koe",
];
