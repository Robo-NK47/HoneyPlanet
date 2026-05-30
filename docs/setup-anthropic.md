# Setting up an Anthropic API key

We use Claude to **extract place mentions** from scraped blog text and **categorize** them
(restaurant / activity / hotel / other), and later to assist planning.

> Needed starting in **Phase 2**. You can skip this until then.

## Steps
1. Sign up / sign in at <https://console.anthropic.com/>.
2. **Add credits / billing** — *Settings → Billing*.
3. **Create a key** — *Settings → API Keys → Create Key*. Copy it now (shown only once).
4. **Save it** to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

## Models we'll use
- **Bulk extraction/categorization:** a cost-effective model (e.g. Claude Sonnet).
- **Planning / reasoning:** a stronger model (e.g. Claude Opus).

Model names are configurable; we'll wire exact IDs in Phase 2.

## Cost
Extraction over a few hundred blog pages is typically a few dollars. `.env` is gitignored.
