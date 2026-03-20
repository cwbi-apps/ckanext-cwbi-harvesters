import logging

from ckan import model
from ckan.plugins import toolkit


log = logging.getLogger(__name__)


@toolkit.chained_action
def harvest_get_notifications_recipients(up_func, context, data_dict):
    """ Harvester plugin notify about harvest jobs only to
            admin users of the related organization.
            Also allow to add custom recipients with this function.

        Get the list of email_list extra at organization

        Return a list of dicts with name and email like
            {'name': 'John', 'email': 'john@source.com'} """

    new_recipients = []
    recipients = up_func(context, data_dict)

    source_id = data_dict['source_id']
    log.info('Adding extra recipients for source {}'.format(source_id))
    context = {"model": model, 'ignore_auth': True}

    try:
        source = toolkit.get_action('harvest_source_show')(context, {'id': source_id})
    except Exception as e:
        log.error('Error at add_extra_notification_recipients: {}'.format(e))
        return recipients

    # GSA saves a custom extra at organizations with the key email_list
    organization = source.get('organization')
    if organization is None:
        log.info('Harvest source without organization: {}'.format(source_id))
        return recipients

    # this not include organization extras
    d = {'id': organization['id']}
    full_organization = toolkit.get_action('organization_show')(context, d)
    extras = full_organization.get('extras', [])
    email_list_extras = [extra['value'] for extra in extras if extra['key'] == 'email_list']
    if len(email_list_extras) > 0:
        org_emails = email_list_extras[0].strip()
        if org_emails:
            org_email_list = org_emails.replace(';', ' ').replace(',', ' ').split()
            for org_email in org_email_list:
                rec = {
                    'name': org_email.lower(),
                    'email': org_email.lower()
                }
                new_recipients.append(rec)

    log.info('Extra recipients for source found: {}'.format(new_recipients))

    recipients += new_recipients
    return recipients