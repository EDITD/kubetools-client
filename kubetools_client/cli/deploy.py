import json
import os

import click

from kubetools_client.cli import cli_bootstrap
from kubetools_client.config import load_kubetools_config
from kubetools_client.deploy import deploy_or_upgrade
from kubetools_client.deploy.build import Build
from kubetools_client.deploy.image import ensure_docker_images
from kubetools_client.deploy.kubernetes.api import (
    delete_deployment,
    delete_job,
    delete_service,
    get_object_name,
    list_deployments,
    list_jobs,
    list_services,
)
from kubetools_client.deploy.kubernetes.config import generate_kubernetes_configs_for_project
from kubetools_client.deploy.util import run_shell_command
from kubetools_client.exceptions import KubeBuildError


@cli_bootstrap.command(help_priority=0)
@click.option(
    '--dry',
    is_flag=True,
    default=False,
    help='Instead of writing objects to Kubernetes, just print them and exit.',
)
@click.option(
    '--replicas',
    type=int,
    default=1,
    help='Default number of replicas for each app.',
)
@click.option(
    '--registry',
    help='Default registry for apps that do not specify.',
)
@click.argument('namespace')
@click.argument(
    'app_dirs',
    nargs=-1,
    type=click.Path(exists=True, file_okay=False),
)
@click.pass_context
def deploy(ctx, dry, replicas, registry, namespace, app_dirs):
    '''
    Deploy an app, or apps, to Kubernetes.
    '''

    if not app_dirs:
        app_dirs = (os.getcwd(),)

    build = Build(
        env=ctx.meta['kube_context'],
        namespace=namespace,
    )

    all_services = []
    all_deployments = []
    all_jobs = []

    for app_dir in app_dirs:
        kubetools_config = load_kubetools_config(
            app_dir,
            env=build.env,
            namespace=build.namespace,
        )

        commit_hash = run_shell_command(
            'git', 'rev-parse', '--short=7', 'HEAD',
            cwd=app_dir,
        ).strip().decode()

        branch_name = run_shell_command(
            'git', 'rev-parse', '--abbrev-ref', 'HEAD',
            cwd=app_dir,
        ).strip().decode()

        annotations = {
            'kubetools/env': build.env,
            'kubetools/namespace': build.namespace,
            'kubetools/git_commit': commit_hash,
            'app.kubernetes.io/managed-by': 'kubetools',
        }

        if branch_name != 'HEAD':
            annotations['kubetools/git_branch'] = branch_name

        try:
            annotations['kubetools/git_tag'] = run_shell_command(
                'git', 'tag', '--points-at', commit_hash,
                cwd=app_dir,
            ).strip().decode()
        except KubeBuildError:
            pass

        labels = {
            'kubetools/project_name': kubetools_config['name'],
        }

        envvars = {
            'KUBE': 'true',
            'KUBE_NAMESPACE': build.namespace,
            'KUBE_ENV': build.env,
        }

        context_to_image = ensure_docker_images(
            kubetools_config, build, app_dir,
            commit_hash=commit_hash,
            default_registry=registry,
        )

        services, deployments, jobs = generate_kubernetes_configs_for_project(
            kubetools_config,
            envvars=envvars,
            context_name_to_image=context_to_image,
            base_annotations=annotations,
            base_labels=labels,
            replicas=replicas,
        )

        all_services.extend(services)
        all_deployments.extend(deployments)
        all_jobs.extend(jobs)

    deploy_function = _dry_deploy_loop if dry else deploy_or_upgrade
    deploy_function(
        build,
        all_services,
        all_deployments,
        all_jobs,
    )


def _dry_deploy_object_loop(object_type, objects):
    name_to_object = {
        get_object_name(obj): obj
        for obj in objects
    }

    while True:
        object_name = click.prompt(
            f'Print {object_type}?',
            type=click.Choice(name_to_object),
            default='exit',
        )

        if object_name == 'exit':
            break

        click.echo(json.dumps(name_to_object[object_name], indent=4))


def _dry_deploy_loop(build, services, deployments, jobs):
    for object_type, objects in (
        ('service', services),
        ('deployment', deployments),
        ('job', jobs),
    ):
        if objects:
            _dry_deploy_object_loop(object_type, objects)


def _get_objects_to_delete(
    object_type, list_objects_function,
    build, remove_all, app_names,
    check_leftovers=True,
):
    objects = list_objects_function(build)
    objects_to_delete = objects.items

    if not remove_all:
        objects_to_delete = list(filter(
            lambda obj: obj.metadata.labels.get('kubetools/name') in app_names,
            objects_to_delete,
        ))

        if check_leftovers:
            object_names_to_delete = set([
                obj.metadata.labels['kubetools/name']
                for obj in objects_to_delete
            ])

            leftover_app_names = set(app_names) - object_names_to_delete
            if leftover_app_names:
                raise click.BadParameter(f'{object_type} not found {leftover_app_names}')

    if objects_to_delete:
        click.echo(f'--> {object_type} to delete:')
        for service in objects_to_delete:
            click.echo(f'    {service.metadata.name}')
        click.echo()

    return objects_to_delete


def _delete_objects(object_type, delete_object_function, objects_to_delete, build):
    for obj in objects_to_delete:
        delete_object_function(build, obj)
        click.echo(f'    {obj.metadata.name} deleted')


@cli_bootstrap.command()
@click.option(
    '-a', '--all', 'remove_all',
    is_flag=True,
    default=False,
    help='Flag to enable removal of all apps within the namespace.',
)
@click.option(
    '-y', '--yes',
    is_flag=True,
    default=False,
    help='Flag to auto-yes remove confirmation step.',
)
@click.argument('namespace')
@click.argument('app_names', nargs=-1)
@click.pass_context
def remove(ctx, remove_all, yes, namespace, app_names):
    '''
    Removes one or more apps from a given namespace.
    '''

    if not app_names and not remove_all:
        raise click.BadParameter('Must either provide app names or --all flag!')
    elif app_names and remove_all:
        raise click.BadParameter('Cannot provide both app naems and --all flag!')

    build = Build(
        env=ctx.meta['kube_context'],
        namespace=namespace,
    )

    services_to_delete = _get_objects_to_delete(
        'Services', list_services,
        build, remove_all, app_names,
    )

    deployments_to_delete = _get_objects_to_delete(
        'Deployments', list_deployments,
        build, remove_all, app_names,
    )

    jobs_to_delete = _get_objects_to_delete(
        'Jobs', list_jobs,
        build, remove_all, app_names,
        check_leftovers=False,
    )

    if not any((services_to_delete, deployments_to_delete, jobs_to_delete)):
        click.echo('Nothing to do!')
        return

    if not yes:
        click.confirm(click.style(
            'Are you sure you wish to DELETE the above resources? This cannot be undone.',
        ))

    _delete_objects('Services', delete_service, services_to_delete, build)
    _delete_objects('Deployments', delete_deployment, deployments_to_delete, build)
    _delete_objects('Jobs', delete_job, jobs_to_delete, build)


# @cli_bootstrap.command()
# @click.argument('app_names', nargs=-1)
# def restart(namespace, app_names):
#     '''
#     Restarts one or more apps in a given namespace.
#     '''


# @cli_bootstrap.command()
# @click.argument('app_names', nargs=-1)
# def cleanup(namespace, app_names):
#     '''
#     Cleans up a namespace by removing any orphaned objects and stale jobs.
#     '''
