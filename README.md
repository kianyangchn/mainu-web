# mainu-web

Web application of Mainu

## Menu processing

- `POST /menu/process` uploads the current batch of menu photos and returns an `upload_session_id` that can be reused without re-uploading the images.
- `POST /menu/retry` rebuilds quick suggestions and the interactive menu using an existing `upload_session_id`.
- `DELETE /menu/session/{id}` clears the session and releases the temporary OpenAI file handles; the frontend calls this when a capture flow is abandoned.

## Internationalization

The frontend now supports locale-aware UI copy (English, Simplified Chinese, Traditional Chinese) driven by gettext catalogs stored under `app/locales/`.

- Locale detection
  - Respects the browser `Accept-Language` header; English is the fallback.
  - `zh-CN`, `zh`, and other Simplified variants resolve to `zh_Hans`.
  - `zh-TW`, `zh-HK`, `zh-Hant`, etc. resolve to `zh_Hant`.

- Extract strings after template changes:
  ```bash
  uv run pybabel extract -F babel.cfg -o app/locales/messages.pot .
  ```
- Update locale catalogs (edit `app/locales/<locale>/LC_MESSAGES/messages.po` as needed) and compile:
  ```bash
  uv run pybabel compile -d app/locales
  ```
- Users can override the UI language via the translate icon in the top bar; the choice is stored in a `ui_locale` cookie and overrides browser negotiation.
- Verify the localized UI with:
  ```bash
  uv run pytest tests/routes/test_home_i18n.py tests/routes/test_menu.py::test_share_view_respects_browser_language
  ```

### Adding a new language

1. Extract messages and initialize the catalog:
   ```bash
   uv run pybabel extract -F babel.cfg -o app/locales/messages.pot .
   uv run pybabel init -i app/locales/messages.pot -d app/locales -l <locale-code>
   ```
2. Translate the generated `messages.po`.
3. Re-run `uv run pybabel compile -d app/locales`.
4. Update `SUPPORTED_LOCALES` in `app/i18n.py` and extend `_map_to_supported_locale` if needed.
