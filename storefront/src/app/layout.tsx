import { getBaseURL } from "@lib/util/env"
import { Metadata } from "next"
import "styles/globals.css"
import React from "react"
import AlexIO from "@modules/common/components/AlexIO"

export const metadata: Metadata = {
  metadataBase: new URL(getBaseURL()),
}

/** Premium fallback config used when VibeCloud backend is unreachable (429, timeout, network error) */
const PREMIUM_FALLBACK_CONFIG = {
  theme: {
    primary_color: "#4F46E5",   // Deep indigo
    secondary_color: "#10B981", // Emerald
    mode: "dark" as const,
  },
}

async function getSDUIConfig(tenantId: number, page: string) {
  const vibecloudUrl = process.env.NEXT_PUBLIC_VIBECLOUD_URL || "http://localhost:8000"

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)

    const res = await fetch(
      `${vibecloudUrl}/api/v1/ui-config/public/${tenantId}/${page}`,
      {
        next: { revalidate: 30 },
        signal: controller.signal,
      }
    )

    clearTimeout(timeout)

    if (!res.ok) {
      if (res.status === 429) {
        console.warn(
          `[VibeCloud SDUI] Rate limited (429) fetching config for tenant ${tenantId}. Using premium fallback.`
        )
      } else {
        console.warn(
          `[VibeCloud SDUI] HTTP ${res.status} fetching config for tenant ${tenantId}. Using premium fallback.`
        )
      }
      return PREMIUM_FALLBACK_CONFIG
    }

    return await res.json()
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.warn(
      `[VibeCloud SDUI] Failed to fetch config for tenant ${tenantId}: ${message}. Using premium fallback.`
    )
    return PREMIUM_FALLBACK_CONFIG
  }
}

export default async function RootLayout(props: { children: React.ReactNode }) {
  const config = await getSDUIConfig(1, "storefront_home")
  const primaryColor = config?.theme?.primary_color || PREMIUM_FALLBACK_CONFIG.theme.primary_color
  const secondaryColor = config?.theme?.secondary_color || PREMIUM_FALLBACK_CONFIG.theme.secondary_color
  const themeMode = config?.theme?.mode || PREMIUM_FALLBACK_CONFIG.theme.mode

  return (
    <html
      lang="en"
      data-mode={themeMode}
      suppressHydrationWarning
      style={{
        "--primary-sdui": primaryColor,
        "--secondary-sdui": secondaryColor,
      } as React.CSSProperties}
    >
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className={`font-sans antialiased theme-transition ${themeMode === "dark" ? "dark" : ""}`}>
        <main className="relative">
          {props.children}
          <AlexIO />
        </main>
      </body>
    </html>
  )
}
