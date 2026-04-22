import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

const pageTitle = process.env.QUARTZ_SITE_TITLE ?? "MCP Research Wiki"
const baseUrl =
  process.env.QUARTZ_BASE_URL ?? "christian-mcp.github.io/llm-wiki-mcp"

const config: QuartzConfig = {
  configuration: {
    pageTitle,
    pageTitleSuffix: "",
    enableSPA: true,
    enablePopovers: true,
    analytics: {
      provider: "plausible",
    },
    locale: "en-US",
    baseUrl,
    ignorePatterns: ["private", "templates", ".obsidian"],
    defaultDateType: "modified",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        header: "IBM Plex Sans",
        body: "IBM Plex Sans",
        code: "IBM Plex Mono",
      },
      colors: {
        lightMode: {
          light: "#f5f1e8",
          lightgray: "#ddd5c7",
          gray: "#9d9483",
          darkgray: "#4f4a41",
          dark: "#201d19",
          secondary: "#175c4c",
          tertiary: "#b76e2d",
          highlight: "rgba(183, 110, 45, 0.12)",
          textHighlight: "#ffe08a99",
        },
        darkMode: {
          light: "#181614",
          lightgray: "#35312c",
          gray: "#837a6b",
          darkgray: "#d8d1c5",
          dark: "#f4efe6",
          secondary: "#78c0a1",
          tertiary: "#e3a86b",
          highlight: "rgba(120, 192, 161, 0.14)",
          textHighlight: "#94780066",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ["frontmatter", "git", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({
        theme: {
          light: "github-light",
          dark: "github-dark",
        },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: true,
        enableRSS: true,
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
    ],
  },
}

export default config
