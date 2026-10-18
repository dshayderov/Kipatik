from app.git.github import GitHubProvider
from app.git.gitlab import GitLabProvider
from app.git.bitbucket import BitbucketProvider
from app.git.gitea import GiteaProvider
from app.git.base import GitProvider
from app.git.models import GitProviderType

class GitProviderFactory:
    @staticmethod
    def get_provider_by_type(provider_type: GitProviderType, token: str = None, api_url: str = None) -> GitProvider:
        if provider_type == GitProviderType.GITHUB:
            return GitHubProvider(token=token)
        if provider_type == GitProviderType.GITLAB:
            return GitLabProvider(token=token)
        if provider_type == GitProviderType.GITLAB_CUSTOM:
            # Для кастомного GitLab извлекаем хост из api_url
            host = "https://gitlab.com"
            if api_url:
                host = api_url.split("/api/v4")[0]
            return GitLabProvider(token=token, host=host)
        if provider_type == GitProviderType.BITBUCKET:
            return BitbucketProvider(access_token=token)
        if provider_type == GitProviderType.GITEA:
            return GiteaProvider(token=token, api_url=api_url)
        return GitHubProvider(token=token) # Fallback

    @staticmethod
    def get_provider(git_url: str) -> GitProvider:
        url_lower = git_url.lower()
        if "github.com" in url_lower:
            return GitHubProvider()
        if "gitlab.com" in url_lower:
            return GitLabProvider()
        if "bitbucket.org" in url_lower:
            return BitbucketProvider()
        # Если не узнали стандартный сервис, пробуем вернуть провайдер по умолчанию 
        # или можно было бы пытаться угадать тип по API ответам
        return GitHubProvider()

# Инстанс фабрики (используется в app.git.services)
git_factory = GitProviderFactory()

def get_git_provider(provider_type: GitProviderType, token: str = None, api_url: str = None) -> GitProvider:
    return GitProviderFactory.get_provider_by_type(provider_type, token, api_url)
