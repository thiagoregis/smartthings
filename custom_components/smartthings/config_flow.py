"""Config flow to configure SmartThings."""
from http import HTTPStatus
import logging

from aiohttp import ClientResponseError
from pysmartthings import APIResponseError, AppOAuth, SmartThings
from pysmartthings.installedapp import format_install_url
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    APP_OAUTH_CLIENT_NAME,
    APP_OAUTH_SCOPES,
    CONF_APP_ID,
    CONF_INSTALLED_APP_ID,
    CONF_LOCATION_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    VAL_UID_MATCHER,
)
from .smartapp import (
    create_app,
    find_app,
    format_unique_id,
    get_webhook_url,
    setup_smartapp,
    setup_smartapp_endpoint,
    update_app,
    validate_webhook_requirements,
)

_LOGGER = logging.getLogger(__name__)


class SmartThingsFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration of SmartThings integrations."""

    VERSION = 2

    def __init__(self):
        """Create a new instance of the flow handler."""
        self.access_token = None
        self.app_id = None
        self.api = None
        self.oauth_client_secret = None
        self.oauth_client_id = None
        self.installed_app_id = None
        self.refresh_token = None
        self.location_id = None
        self.entry = None

    async def async_step_import(self, user_input=None):
        """Occurs when a previously entry setup fails and is re-initiated."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        """Inicia o fluxo OAuth2 para login na conta Samsung."""
        await setup_smartapp_endpoint(self.hass)
        webhook_url = get_webhook_url(self.hass)

        # Abort if the webhook is invalid
        if not validate_webhook_requirements(self.hass):
            return self.async_abort(
                reason="invalid_webhook_url",
                description_placeholders={
                    "webhook_url": webhook_url,
                    "component_url": "https://www.home-assistant.io/integrations/smartthings/",
                },
            )

        # Mostra tela inicial com botão para login OAuth2
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                description_placeholders={"webhook_url": webhook_url},
            )

        # Inicia o fluxo OAuth2
        return await self.async_step_oauth()

    async def async_step_oauth(self, user_input=None):
        """Redireciona o usuário para o login OAuth2 da Samsung."""
        # Substitua pelos valores reais do seu app registrado no SmartThings
        client_id = "SUA_CLIENT_ID"
        redirect_uri = "https://meu-home-assistant.com/auth/external/callback"
        scope = "r:devices:* x:devices:* r:locations:* x:locations:*"
        oauth_url = (
            f"https://auth-global.api.smartthings.com/oauth/authorize?"
            f"client_id={client_id}&response_type=code&scope={scope}&redirect_uri={redirect_uri}"
        )
        return self.async_external_step(step_id="oauth", url=oauth_url)

    async def async_step_code(self, user_input=None):
        """Recebe o código de autorização e troca por access_token."""
        import aiohttp
        errors = {}
        if user_input is None or "code" not in user_input:
            errors["base"] = "missing_code"
            return self.async_show_form(step_id="code", errors=errors)

        code = user_input["code"]
        client_id = "SUA_CLIENT_ID"  # Substitua pelo seu client_id
        client_secret = "SUA_CLIENT_SECRET"  # Substitua pelo seu client_secret
        redirect_uri = "https://meu-home-assistant.com/auth/external/callback"  # Substitua pelo seu redirect_uri

        token_url = "https://auth-global.api.smartthings.com/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(token_url, data=data) as resp:
                resp_json = await resp.json()
                if resp.status != 200:
                    errors["base"] = resp_json.get("error_description", "token_exchange_failed")
                    return self.async_show_form(step_id="code", errors=errors)
                self.access_token = resp_json["access_token"]
                self.refresh_token = resp_json.get("refresh_token")
        except Exception as ex:
            errors["base"] = "token_exchange_exception"
            _LOGGER.error("Erro ao trocar código por token: %s", ex)
            return self.async_show_form(step_id="code", errors=errors)

        return await self.async_step_select_location()

    async def async_step_reauth(self, entry_data):
        """Handle configuration by re-auth."""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_oauth()

    # async_step_pat removido, fluxo agora é OAuth2

    async def async_step_select_location(self, user_input=None):
        """Ask user to select the location to setup."""
        if user_input is None or CONF_LOCATION_ID not in user_input:
            # Get available locations
            existing_locations = [
                entry.data[CONF_LOCATION_ID] for entry in self._async_current_entries()
            ]
            _LOGGER.debug("Chamando self.api.locations() com APP_ID: %s", self.app_id)
            try:
                client_id = "hass-smartthings"  # App oficial Home Assistant
                client_secret = "hass-smartthings"  # App oficial Home Assistant
                redirect_uri = "https://www.home-assistant.io/auth/external/callback"  # App oficial Home Assistant
                _LOGGER.error("Erro ao chamar self.api.locations(): %s", ex)
                locations = []
            _LOGGER.debug("Localizações já configuradas: %s", existing_locations)
            locations_options = {
                if location.location_id not in existing_locations
            }
            _LOGGER.debug("Localizações disponíveis para configuração: %s", locations_options)
            if not locations_options:
                _LOGGER.error("Nenhuma localização disponível. Todas podem já estar configuradas ou a API retornou lista vazia.")
                return self.async_abort(reason="no_available_locations")

            return self.async_show_form(
                step_id="select_location",
                data_schema=vol.Schema(
                    {vol.Required(CONF_LOCATION_ID): vol.In(locations_options)}
                ),
            )

        self.location_id = user_input[CONF_LOCATION_ID]
        await self.async_set_unique_id(format_unique_id(self.app_id, self.location_id))
                client_id = "hass-smartthings"  # App oficial Home Assistant
                client_secret = "hass-smartthings"  # App oficial Home Assistant
                redirect_uri = "https://www.home-assistant.io/auth/external/callback"  # App oficial Home Assistant
        """Wait for the user to authorize the app installation."""
        user_input = {} if user_input is None else user_input
        self.installed_app_id = user_input.get(CONF_INSTALLED_APP_ID)
        self.refresh_token = user_input.get(CONF_REFRESH_TOKEN)
        if self.installed_app_id is None:
            # Launch the external setup URL
            url = format_install_url(self.app_id, self.location_id)
            return self.async_external_step(step_id="authorize", url=url)

        return self.async_external_step_done(next_step_id="install")

    def _show_step_pat(self, errors):
        if self.access_token is None:
            # Get the token from an existing entry to make it easier to setup multiple locations.
            self.access_token = next(
                (
                    entry.data.get(CONF_ACCESS_TOKEN)
                    for entry in self._async_current_entries()
                ),
                None,
            )

        return self.async_show_form(
            step_id="pat",
            data_schema=vol.Schema(
                {vol.Required(CONF_ACCESS_TOKEN, default=self.access_token): str}
            ),
            errors=errors,
            description_placeholders={
                "token_url": "https://account.smartthings.com/tokens",
                "component_url": "https://www.home-assistant.io/integrations/smartthings/",
            },
        )

    async def async_step_install(self, data=None):
        """Create a config entry at completion of a flow and authorization of the app."""
        data = {
            CONF_ACCESS_TOKEN: self.access_token,
            CONF_REFRESH_TOKEN: self.refresh_token,
            CONF_CLIENT_ID: self.oauth_client_id,
            CONF_CLIENT_SECRET: self.oauth_client_secret,
            CONF_LOCATION_ID: self.location_id,
            CONF_APP_ID: self.app_id,
            CONF_INSTALLED_APP_ID: self.installed_app_id,
        }

        location = await self.api.location(data[CONF_LOCATION_ID])

        if self.source == config_entries.SOURCE_REAUTH:
            self.hass.config_entries.async_update_entry(
                self.entry,
                data=data,
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.entry.entry_id)
            )
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(title=location.name, data=data)
