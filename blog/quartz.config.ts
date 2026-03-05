import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * Quartz 4 Configuration
 *
 * See https://quartz.jzhao.xyz/configuration for more information.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "Emerge Devlog",
    pageTitleSuffix: " | Emerge",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "en-US",
    // Inferred from the origin repo's GitHub Pages URL. Update if you deploy elsewhere.
    baseUrl: "emerge-world.github.io/emerge",
    ignorePatterns: ["private", "templates", ".obsidian"],
    defaultDateType: "created",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        title: {
          name: "Atkinson Hyperlegible Next",
          weights: [700],
        },
        header: {
          name: "Atkinson Hyperlegible Next",
          weights: [600, 700],
        },
        body: {
          name: "Atkinson Hyperlegible Next",
          weights: [400, 500, 600],
          includeItalic: true,
        },
        code: "IBM Plex Mono",
      },
      colors: {
        lightMode: {
          light: "#f6f1e8",
          lightgray: "#ddd4c5",
          gray: "#948977",
          darkgray: "#4e473e",
          dark: "#181613",
          secondary: "#275b63",
          tertiary: "#a36b2c",
          highlight: "rgba(39, 91, 99, 0.12)",
          textHighlight: "#f1d26a88",
        },
        darkMode: {
          light: "#17191b",
          lightgray: "#2b3135",
          gray: "#6d777d",
          darkgray: "#d9d2c4",
          dark: "#f4efe6",
          secondary: "#8dbfc4",
          tertiary: "#d69a56",
          highlight: "rgba(141, 191, 196, 0.15)",
          textHighlight: "#c8ac2f66",
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
      // Disabled for local preview because it fetches remote fonts during build.
      // Re-enable if you want generated OG images in builds with network access.
      // Plugin.CustomOgImages(),
    ],
  },
}

export default config
