import click

from kubetools_client.exceptions import KubeDevError
from kubetools_client.settings import get_settings

from . import dev
from .config import find_container_for_config
from .container_util import (
    build_containers,
    destroy_containers,
    get_containers_status,
    print_containers,
    run_container,
    start_containers,
    stop_containers,
    up_containers,
)


@dev.command()
@click.option(
    '--active',
    is_flag=True,
)
@click.pass_obj
def status(kubetools_config, active):
    '''
    Display info on the local dev environment.
    '''

    click.echo('--> Loading environments...')
    print_containers(kubetools_config, all_environments=not active)


@dev.command()
@click.argument('containers', nargs=-1)
@click.pass_obj
def destroy(kubetools_config, containers=None):
    '''
    Stop and remove containers.
    '''

    click.echo('--> Destroying containers')
    destroy_containers(kubetools_config, containers)
    click.echo('--> Dev environment down')


@dev.command()
@click.argument('containers', nargs=-1)
@click.pass_obj
def start(kubetools_config, containers=None):
    '''
    Start stopped containers.
    '''

    click.echo('--> Starting containers')
    start_containers(kubetools_config, containers)
    click.echo('--> Containers started')
    click.echo()

    # Always print all containers
    print_containers(kubetools_config)


@dev.command()
@click.argument('containers', nargs=-1)
@click.pass_obj
def stop(kubetools_config, containers=None):
    '''
    Stop running containers.
    '''

    click.echo('--> Stopping containers')
    stop_containers(kubetools_config, containers)
    click.echo('--> Containers stopped')
    click.echo()

    # Always print all containers
    print_containers(kubetools_config)


@dev.command()
@click.argument('containers', nargs=-1)
@click.option('destroy_containers', '--destroy', is_flag=True)
@click.option('--no-upgrade', is_flag=True)
@click.pass_obj
@click.pass_context
def reload(
    ctx, kubetools_config,
    containers=None,
    destroy_containers=False,
    no_upgrade=False,
):
    '''
    Reload the dev environment.
    '''

    if destroy_containers:
        ctx.invoke(destroy, containers=containers)
    else:
        ctx.invoke(stop, containers=containers)

    click.echo()

    # Then up with all the arguments/options
    ctx.invoke(up, containers=containers, no_upgrade=no_upgrade)


@dev.command()
@click.argument('containers', nargs=-1)
@click.option(
    '--no-upgrade',
    is_flag=True,
    help='Disable running of any upgrades.',
)
@click.pass_obj
def up(
    kubetools_config,
    containers=None,
    no_upgrade=False,
    is_testing=False,
):
    '''
    Create and/or start containers and run any upgrades.
    '''

    upgrade = not no_upgrade
    container_statuses = get_containers_status(kubetools_config)

    # Figure out containers, if any, to upgrade
    upgrade_containers = []
    if not no_upgrade:
        if containers:
            upgrade_containers = containers
        else:
            upgrade_containers = [
                container_name
                for container_name, container in container_statuses.items()
            ]

    # Build the container(s)
    click.echo('--> Building any out of date containers')
    build_containers(kubetools_config, containers)
    click.echo()

    # Up the container(s)
    click.echo('--> Starting containers')
    up_containers(kubetools_config, containers)

    click.echo('--> Dev environment up')
    click.echo()

    if upgrade_containers:
        click.echo('--> Running upgrades')

        for upgrade in kubetools_config.get('upgrades', []):
            apply_when_testing = upgrade.get('conditions', {}).get('test', True)
            if is_testing and not apply_when_testing:
                continue

            container_name = find_container_for_config(
                kubetools_config, upgrade,
            )

            if containers and container_name not in upgrade_containers:
                continue

            click.echo('--> Running upgrade {0} in container {1}'.format(
                click.style(upgrade.get(
                    'name',
                    ' '.join(upgrade['command']),
                ), bold=True),
                container_name,
            ))

            run_container(
                kubetools_config,
                container_name,
                upgrade['command'],
            )
            click.echo()

    # Always print all containers
    print_containers(kubetools_config)
    click.echo()

    click.echo(''.join((
        click.style('Use `', 'blue'),
        click.style('ktd logs', bold=True),
        click.style('` to see what the containers are up to', 'blue'),
    )))
    click.echo(''.join((
        click.style('Use `', 'blue'),
        click.style('ktd attach <container>', bold=True),
        click.style('` to attach to a running container', 'blue'),
    )))


@dev.command()
@click.argument('arguments', nargs=-1)
@click.option(
    '--keep-containers',
    is_flag=True,
    help='Don\'t remove any test environment containers after completion',
)
@click.pass_obj
@click.pass_context
def test(ctx, kubetools_config, keep_containers=False, arguments=None):
    '''
    Execute tests in a new environment.

    You can pass extra arguments to the test command like so:

    ktd test -- --ipdb-failures
    '''

    DEV_DEFAULT_ENV = get_settings().DEV_DEFAULT_ENV

    # Set the env to test if not already overridden
    if kubetools_config.get('env', DEV_DEFAULT_ENV) == DEV_DEFAULT_ENV:
        kubetools_config['env'] = 'test'

    try:
        ctx.invoke(up, is_testing=True)

        click.echo()
        click.echo('--> Executing tests...')

        tests = kubetools_config.get('tests')

        if not tests:
            raise KubeDevError('No tests provided in kubetools config!')

        for test in tests:
            command = test['command']

            if arguments:
                command.extend(arguments)

            container_name = find_container_for_config(
                kubetools_config, test,
            )

            click.echo('--> Running test {0} in container {1}'.format(
                click.style(test.get(
                    'name',
                    ' '.join(command),
                ), bold=True),
                container_name,
            ))

            run_container(
                kubetools_config,
                container_name,
                command,
                envars=test.get('environment', []),
            )
            click.echo()

    except Exception:
        click.echo(click.style('Exception!', 'red', bold=True))
        raise

    else:
        click.echo(click.style('--> Tests complete', 'green'))

    finally:
        if not keep_containers:
            ctx.invoke(destroy)
