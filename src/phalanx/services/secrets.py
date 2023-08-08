"""Service to manipulate Phalanx secrets."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml
from pydantic import SecretStr

from ..exceptions import UnresolvedSecretsError
from ..models.applications import ApplicationInstance
from ..models.environments import Environment
from ..models.secrets import ResolvedSecret, Secret, SourceSecretGenerateRules
from ..storage.config import ConfigStorage
from ..storage.vault import VaultStorage
from ..yaml import YAMLFoldedString

__all__ = ["SecretsService"]


class SecretsService:
    """Service to manipulate Phalanx secrets.

    Parameters
    ----------
    config_storage
        Storage object for the Phalanx configuration.
    vault_storage
        Storage object for Vault.
    """

    def __init__(
        self, config_storage: ConfigStorage, vault_storage: VaultStorage
    ) -> None:
        self._config = config_storage
        self._vault = vault_storage

    def audit(self, env_name: str) -> str:
        """Compare existing secrets to configuration and report problems.

        Parameters
        ----------
        env_name
            Name of the environment to audit.

        Returns
        -------
        str
            Audit report as a text document.
        """
        environment = self._config.load_environment(env_name)
        vault_client = self._vault.get_vault_client(environment)

        # Retrieve all the current secrets from Vault and resolve all of the
        # secrets.
        secrets = environment.all_secrets()
        vault_secrets = vault_client.get_environment_secrets(environment)
        resolved = self._resolve_secrets(secrets, environment, vault_secrets)

        # Compare the resolved secrets to the Vault data.
        missing = []
        mismatch = []
        unknown = []
        for app_name, values in resolved.items():
            for key, value in values.items():
                if key in vault_secrets[app_name]:
                    if value.value:
                        expected = value.value.get_secret_value()
                    else:
                        expected = None
                    vault = vault_secrets[app_name][key].get_secret_value()
                    if expected != vault:
                        import logging

                        logging.error("mismatch %s %s", expected, vault)
                        mismatch.append(f"{app_name} {key}")
                    del vault_secrets[app_name][key]
                else:
                    missing.append(f"{app_name} {key}")
        unknown = [f"{a} {k}" for a, lv in vault_secrets.items() for k in lv]

        # Generate the textual report.
        report = ""
        if missing:
            report += "Missing secrets:\n• " + "\n• ".join(missing) + "\n"
        if mismatch:
            report += "Incorrect secrets:\n• " + "\n• ".join(mismatch) + "\n"
        if unknown:
            unknown_str = "\n  ".join(unknown)
            report += "Unknown secrets in Vault:\n• " + unknown_str + "\n"
        return report

    def generate_static_template(self, env_name: str) -> str:
        """Generate a template for providing static secrets.

        The template provides space for all static secrets required for a
        given environment. The resulting file, once the values have been
        added, can be used as input to other secret commands instead of an
        external secret source such as 1Password.

        Parameters
        ----------
        env_name
            Name of the environment.

        Returns
        -------
        dict
            YAML template the user can fill out, as a string.
        """
        secrets = self.list_secrets(env_name)
        template: defaultdict[str, dict[str, dict[str, str | None]]]
        template = defaultdict(dict)
        for secret in secrets:
            static = not (secret.copy_rules or secret.generate or secret.value)
            if static:
                template[secret.application][secret.key] = {
                    "description": YAMLFoldedString(secret.description),
                    "value": None,
                }
        return yaml.dump(template, width=72)

    def list_secrets(self, env_name: str) -> list[Secret]:
        """List all required secrets for the given environment.

        Parameters
        ----------
        env_name
            Name of the environment.

        Returns
        -------
        list of Secret
            Secrets required for the given environment.
        """
        environment = self._config.load_environment(env_name)
        return environment.all_secrets()

    def save_vault_secrets(self, env_name: str, path: Path) -> None:
        """Generate JSON files containing the Vault secrets for an environment.

        One file per application with secrets will be written to the provided
        path. Each file will be named after the application with ``.json``
        appended, and will contain the secret values for that application.
        Secrets that are required but have no known value will be written as
        null.

        Parameters
        ----------
        env_name
            Name of the environment.
        path
            Output path.
        """
        environment = self._config.load_environment(env_name)
        vault_client = self._vault.get_vault_client(environment)
        vault_secrets = vault_client.get_environment_secrets(environment)
        for app_name, values in vault_secrets.items():
            app_secrets: dict[str, str | None] = {}
            for key, secret in values.items():
                if secret:
                    app_secrets[key] = secret.get_secret_value()
                else:
                    app_secrets[key] = None
            with (path / f"{app_name}.json").open("w") as fh:
                json.dump(app_secrets, fh, indent=2)

    def _resolve_secrets(
        self,
        secrets: list[Secret],
        environment: Environment,
        vault_secrets: dict[str, dict[str, SecretStr]],
    ) -> dict[str, dict[str, ResolvedSecret]]:
        """Resolve the secrets for a Phalanx environment.

        Resolving secrets is the process where the secret configuration is
        resolved using per-environment Helm chart values to generate the list
        of secrets required for a given environment and their values.

        Parameters
        ----------
        secrets
            Secret configuration by application and key.
        environment
            Phalanx environment for which to resolve secrets.
        vault_secrets
            Current values from Vault. These will be used if compatible with
            the secret definitions.

        Returns
        -------
        dict
            Resolved secrets by application and secret key.

        Raises
        ------
        UnresolvedSecretsError
            Raised if some secrets could not be resolved.
        """
        resolved: defaultdict[str, dict[str, ResolvedSecret]]
        resolved = defaultdict(dict)
        unresolved = list(secrets)
        left = len(unresolved)
        while unresolved:
            secrets = unresolved
            unresolved = []
            for config in secrets:
                vault_values = vault_secrets[config.application]
                secret = self._resolve_secret(
                    config=config,
                    instance=environment.applications[config.application],
                    resolved=resolved,
                    current_value=vault_values.get(config.key),
                )
                if secret:
                    resolved[secret.application][secret.key] = secret
                else:
                    unresolved.append(config)
            if len(unresolved) >= left:
                raise UnresolvedSecretsError(unresolved)
            left = len(unresolved)
        return resolved

    def _resolve_secret(
        self,
        *,
        config: Secret,
        instance: ApplicationInstance,
        resolved: dict[str, dict[str, ResolvedSecret]],
        current_value: SecretStr | None,
    ) -> ResolvedSecret | None:
        """Resolve a single secret.

        Parameters
        ----------
        config
            Configuration of the secret.
        instance
            Application instance owning this secret.
        resolved
            Other secrets for that environment that have already been
            resolved.
        current_value
            Current secret value in Vault, if known.

        Returns
        -------
        ResolvedSecret or None
            Resolved value of the secret, or `None` if the secret cannot yet
            be resolved (because, for example, the secret from which it is
            copied has not yet been resolved).
        """
        # If a value was already provided, this is the easy case.
        if config.value:
            return ResolvedSecret(
                key=config.key,
                application=config.application,
                value=config.value,
            )

        # Do copying or generation if configured.
        if config.copy_rules:
            application = config.copy_rules.application
            other = resolved.get(application, {}).get(config.copy_rules.key)
            if not other:
                return None
            return ResolvedSecret(
                key=config.key,
                application=config.application,
                value=other.value,
            )
        if config.generate and not current_value:
            if isinstance(config.generate, SourceSecretGenerateRules):
                other_key = config.generate.source
                other = resolved.get(config.application, {}).get(other_key)
                if not (other and other.value):
                    return None
                value = config.generate.generate(other.value)
            else:
                value = config.generate.generate()
            return ResolvedSecret(
                key=config.key,
                application=config.application,
                value=value,
            )

        # The remaining case is that the secret is a static secret or a
        # generated secret for which we already have a value.
        return ResolvedSecret(
            key=config.key, application=config.application, value=current_value
        )
