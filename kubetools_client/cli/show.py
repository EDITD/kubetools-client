import click

from tabulate import tabulate

from kubetools_client.constants import (
    GIT_BRANCH_ANNOTATION_KEY,
    GIT_COMMIT_ANNOTATION_KEY,
    GIT_TAG_ANNOTATION_KEY,
    NAME_LABEL_KEY,
    PROJECT_NAME_LABEL_KEY,
    ROLE_LABEL_KEY,
)
from kubetools_client.deploy.build import Build
from kubetools_client.deploy.kubernetes.api import (
    get_object_name,
    is_kubetools_object,
    list_deployments,
    list_jobs,
    list_replica_sets,
    list_services,
)

from . import cli_bootstrap


def _get_service_meta(service):
    meta_items = []
    for port in service.spec.ports:
        meta_items.append(f'port={port.port}, nodePort={port.node_port}')
    return ''.join(meta_items)


def _print_items2(items, meta_function=None):
    for item in items:
        name = click.style(get_object_name(item), bold=True)

        project_name = item.metadata.labels.get(PROJECT_NAME_LABEL_KEY, 'unknown')
        meta = f'project={project_name}'

        if meta_function:
            meta = f'{meta}, {meta_function(item)}'

        click.echo(f'    {name} ({meta})')


def _print_items(items, header_to_getter=None):
    header_to_getter = header_to_getter or {}

    headers = ['Name', 'Role', 'Project']
    headers.extend(header_to_getter.keys())
    headers = [click.style(header, bold=True) for header in headers]

    rows = []
    for item in items:
        row = [get_object_name(item)]

        row.append(item.metadata.labels.get(ROLE_LABEL_KEY))

        if not is_kubetools_object(item):
            row.append(click.style('NOT MANAGED BY KUBETOOLS', 'yellow'))
        else:
            row.append(item.metadata.labels.get(PROJECT_NAME_LABEL_KEY, 'unknown'))

        for getter in header_to_getter.values():
            row.append(getter(item))

        rows.append(row)

    click.echo(tabulate(rows, headers=headers, tablefmt='simple'))


def _get_node_ports(item):
    node_ports = []
    for port in item.spec.ports:
        if port.node_port:
            node_ports.append(f'{port.port}:{port.node_port}')
        else:
            node_ports.append(f'{port.port}')

    return ', '.join(node_ports)


def _get_ready_status(item):
    return f'{item.status.ready_replicas or 0}/{item.status.replicas}'


def _get_version_info(item):
    annotations = item.metadata.annotations
    bits = []
    for name, key in (
        ('branch', GIT_BRANCH_ANNOTATION_KEY),
        ('tag', GIT_TAG_ANNOTATION_KEY),
        ('commit', GIT_COMMIT_ANNOTATION_KEY),
    ):
        data = annotations.get(key)
        if data:
            bits.append(f'{name}={data}')

    return ', '.join(bits)


def _get_completion_status(item):
    return f'{item.status.succeeded}/{item.spec.completions}'


@cli_bootstrap.command(help_priority=3)
@click.argument('namespace')
@click.argument('app', required=False)
@click.pass_context
def show(ctx, namespace, app):
    '''
    Show running apps in a given namespace.
    '''

    build = Build(
        env=ctx.meta['kube_context'],
        namespace=namespace,
    )

    if app:
        click.echo(f'--> Filtering by app={app}')

    services = list_services(build)

    if services:
        if app:
            services = [s for s in services if get_object_name(s) == app]

        click.echo(f'--> {len(services)} Services')
        _print_items(services, {
            'Port(:nodePort)': _get_node_ports,
        })
        click.echo()

    deployments = list_deployments(build)

    if deployments:
        if app:
            deployments = [d for d in deployments if get_object_name(d) == app]

        click.echo(f'--> {len(deployments)} Deployments')

        _print_items(deployments, {
            'Ready': _get_ready_status,
            'Version': _get_version_info,
        })
        click.echo()

    if app:
        replica_sets = list_replica_sets(build)
        replica_sets = [
            r for r in replica_sets
            if r.metadata.labels.get(NAME_LABEL_KEY) == app
        ]

        click.echo(f'--> {len(replica_sets)} Replica sets')
        _print_items(replica_sets, {
            'Ready': _get_ready_status,
            'Version': _get_version_info,
        })
        click.echo()
    else:
        jobs = list_jobs(build)
        if jobs:
            click.echo(f'--> {len(jobs)} Jobs')
            _print_items(jobs, {
                'Completions': _get_completion_status,
            })
            click.echo()