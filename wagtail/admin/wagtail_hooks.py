from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from draftjs_exporter.dom import DOM

import wagtail.admin.rich_text.editors.draftail.features as draftail_features

from wagtail.admin.auth import user_has_any_page_permission
from wagtail.admin.localization import get_available_admin_languages, get_available_admin_time_zones
from wagtail.admin.menu import MenuItem, SubmenuMenuItem, reports_menu, settings_menu
from wagtail.admin.navigation import get_explorable_root_page
from wagtail.admin.rich_text import (
    HalloFormatPlugin, HalloHeadingPlugin, HalloListPlugin, HalloPlugin)
from wagtail.admin.rich_text.converters.contentstate import link_entity
from wagtail.admin.rich_text.converters.editor_html import (
    LinkTypeRule, PageLinkHandler, WhitelistRule)
from wagtail.admin.rich_text.converters.html_to_contentstate import (
    BlockElementHandler, ExternalLinkElementHandler, HorizontalRuleHandler,
    InlineStyleElementHandler, ListElementHandler, ListItemElementHandler, PageLinkElementHandler)
from wagtail.admin.search import SearchArea
from wagtail.admin.site_summary import PagesSummaryItem
from wagtail.admin.views.account import email_management_enabled, password_management_enabled
from wagtail.admin.viewsets import viewsets
from wagtail.admin.widgets import Button, ButtonWithDropdownFromHook, PageListingButton
from wagtail.core import hooks
from wagtail.core.models import UserPagePermissionsProxy
from wagtail.core.permissions import (
    collection_permission_policy, task_permission_policy, workflow_permission_policy)
from wagtail.core.whitelist import allow_without_attributes, attribute_rule, check_url


class ExplorerMenuItem(MenuItem):
    template = 'wagtailadmin/shared/explorer_menu_item.html'

    def is_shown(self, request):
        return user_has_any_page_permission(request.user)

    def get_context(self, request):
        context = super().get_context(request)
        start_page = get_explorable_root_page(request.user)

        if start_page:
            context['start_page_id'] = start_page.id

        return context


@hooks.register('register_admin_menu_item')
def register_explorer_menu_item():
    return ExplorerMenuItem(
        _('Pages'), reverse('wagtailadmin_explore_root'),
        name='explorer',
        icon_name='folder-open-inverse',
        order=100)


class SettingsMenuItem(SubmenuMenuItem):
    template = 'wagtailadmin/shared/menu_settings_menu_item.html'


@hooks.register('register_admin_menu_item')
def register_settings_menu():
    return SettingsMenuItem(
        _('Settings'),
        settings_menu,
        icon_name='cogs',
        order=10000)


@hooks.register('register_permissions')
def register_permissions():
    return Permission.objects.filter(content_type__app_label='wagtailadmin', codename='access_admin')


class PageSearchArea(SearchArea):
    def __init__(self):
        super().__init__(
            _('Pages'), reverse('wagtailadmin_pages:search'),
            name='pages',
            icon_name='folder-open-inverse',
            order=100)

    def is_shown(self, request):
        return user_has_any_page_permission(request.user)


@hooks.register('register_admin_search_area')
def register_pages_search_area():
    return PageSearchArea()


class CollectionsMenuItem(MenuItem):
    def is_shown(self, request):
        return collection_permission_policy.user_has_any_permission(
            request.user, ['add', 'change', 'delete']
        )


@hooks.register('register_settings_menu_item')
def register_collections_menu_item():
    return CollectionsMenuItem(_('Collections'), reverse('wagtailadmin_collections:index'), icon_name='folder-open-1', order=700)


class WorkflowsMenuItem(MenuItem):
    def is_shown(self, request):
        return workflow_permission_policy.user_has_any_permission(
            request.user, ['add', 'change', 'delete']
        )


class WorkflowTasksMenuItem(MenuItem):
    def is_shown(self, request):
        return task_permission_policy.user_has_any_permission(
            request.user, ['add', 'change', 'delete']
        )


@hooks.register('register_settings_menu_item')
def register_workflows_menu_item():
    return WorkflowsMenuItem(_('Workflows'), reverse('wagtailadmin_workflows:index'), icon_name='tasks', order=100)


@hooks.register('register_settings_menu_item')
def register_workflow_tasks_menu_item():
    return WorkflowTasksMenuItem(_('Workflow tasks'), reverse('wagtailadmin_workflows:task_index'), icon_name='thumbtack', order=150)


@hooks.register('register_page_listing_buttons')
def page_listing_buttons(page, page_perms, is_parent=False, next_url=None):
    if page_perms.can_edit():
        yield PageListingButton(
            _('Edit'),
            reverse('wagtailadmin_pages:edit', args=[page.id]),
            attrs={'aria-label': _("Edit '%(title)s'") % {'title': page.get_admin_display_title()}},
            priority=10
        )
    if page.has_unpublished_changes and page.is_previewable():
        yield PageListingButton(
            _('View draft'),
            reverse('wagtailadmin_pages:view_draft', args=[page.id]),
            attrs={
                'aria-label': _("Preview draft version of '%(title)s'") % {'title': page.get_admin_display_title()},
                'target': '_blank', 'rel': 'noopener noreferrer'
            },
            priority=20
        )
    if page.live and page.url:
        yield PageListingButton(
            _('View live'),
            page.url,
            attrs={
                'target': "_blank", 'rel': 'noopener noreferrer',
                'aria-label': _("View live version of '%(title)s'") % {'title': page.get_admin_display_title()},
            },
            priority=30
        )
    if page_perms.can_add_subpage():
        if is_parent:
            yield Button(
                _('Add child page'),
                reverse('wagtailadmin_pages:add_subpage', args=[page.id]),
                attrs={
                    'aria-label': _("Add a child page to '%(title)s' ") % {'title': page.get_admin_display_title()},
                },
                classes={'button', 'button-small', 'bicolor', 'icon', 'white', 'icon-plus'},
                priority=40
            )
        else:
            yield PageListingButton(
                _('Add child page'),
                reverse('wagtailadmin_pages:add_subpage', args=[page.id]),
                attrs={'aria-label': _("Add a child page to '%(title)s' ") % {'title': page.get_admin_display_title()}},
                priority=40
            )

    yield ButtonWithDropdownFromHook(
        _('More'),
        hook_name='register_page_listing_more_buttons',
        page=page,
        page_perms=page_perms,
        is_parent=is_parent,
        next_url=next_url,
        attrs={
            'target': '_blank', 'rel': 'noopener noreferrer',
            'title': _("View more options for '%(title)s'") % {'title': page.get_admin_display_title()}
        },
        priority=50
    )


@hooks.register('register_page_listing_more_buttons')
def page_listing_more_buttons(page, page_perms, is_parent=False, next_url=None):
    if page_perms.can_move():
        yield Button(
            _('Move'),
            reverse('wagtailadmin_pages:move', args=[page.id]),
            attrs={"title": _("Move page '%(title)s'") % {'title': page.get_admin_display_title()}},
            priority=10
        )
    if page_perms.can_copy():
        url = reverse('wagtailadmin_pages:copy', args=[page.id])
        if next_url:
            url += '?' + urlencode({'next': next_url})

        urlencode
        yield Button(
            _('Copy'),
            url,
            attrs={'title': _("Copy page '%(title)s'") % {'title': page.get_admin_display_title()}},
            priority=20
        )
    if page_perms.can_delete():
        url = reverse('wagtailadmin_pages:delete', args=[page.id])
        if next_url:
            url += '?' + urlencode({'next': next_url})

        yield Button(
            _('Delete'),
            url,
            attrs={'title': _("Delete page '%(title)s'") % {'title': page.get_admin_display_title()}},
            priority=30
        )
    if page_perms.can_unpublish():
        url = reverse('wagtailadmin_pages:unpublish', args=[page.id])
        if next_url:
            url += '?' + urlencode({'next': next_url})

        yield Button(
            _('Unpublish'),
            url,
            attrs={'title': _("Unpublish page '%(title)s'") % {'title': page.get_admin_display_title()}},
            priority=40
        )

    if page_perms.can_view_revisions():
        yield Button(
            _('History'),
            reverse('wagtailadmin_pages:history', args=[page.id]),
            attrs={'title': _("View page history for '%(title)s'") % {'title': page.get_admin_display_title()}},
            priority=50
        )


@hooks.register('register_admin_urls')
def register_viewsets_urls():
    viewsets.populate()
    return viewsets.get_urlpatterns()


@hooks.register('register_account_menu_item')
def register_account_set_profile_picture(request):
    return {
        'url': reverse('wagtailadmin_account_change_avatar'),
        'label': _('Set profile picture'),
        'help_text': _("Change your profile picture.")
    }


@hooks.register('register_account_menu_item')
def register_account_change_email(request):
    if email_management_enabled():
        return {
            'url': reverse('wagtailadmin_account_change_email'),
            'label': _('Change email'),
            'help_text': _('Change the email address linked to your account.'),
        }


@hooks.register('register_account_menu_item')
def register_account_change_password(request):
    if password_management_enabled() and request.user.has_usable_password():
        return {
            'url': reverse('wagtailadmin_account_change_password'),
            'label': _('Change password'),
            'help_text': _('Change the password you use to log in.'),
        }


@hooks.register('register_account_menu_item')
def register_account_notification_preferences(request):
    user_perms = UserPagePermissionsProxy(request.user)
    if user_perms.can_edit_pages() or user_perms.can_publish_pages():
        return {
            'url': reverse('wagtailadmin_account_notification_preferences'),
            'label': _('Notification preferences'),
            'help_text': _('Choose which email notifications to receive.'),
        }


@hooks.register('register_account_menu_item')
def register_account_preferred_language_preferences(request):
    if len(get_available_admin_languages()) > 1:
        return {
            'url': reverse('wagtailadmin_account_language_preferences'),
            'label': _('Language preferences'),
            'help_text': _('Choose the language you want to use here.'),
        }


@hooks.register('register_account_menu_item')
def register_account_current_time_zone(request):
    if len(get_available_admin_time_zones()) > 1:
        return {
            'url': reverse('wagtailadmin_account_current_time_zone'),
            'label': _('Current Time Zone'),
            'help_text': _('Choose your current time zone.'),
        }


@hooks.register('register_account_menu_item')
def register_account_change_name(request):
    return {
        'url': reverse('wagtailadmin_account_change_name'),
        'label': _('Change name'),
        'help_text': _('Change your first and last name on your account.'),
    }


@hooks.register('register_rich_text_features')
def register_core_features(features):
    # Hallo.js
    features.register_editor_plugin(
        'hallo', 'hr',
        HalloPlugin(
            name='hallohr',
            js=['wagtailadmin/js/hallo-plugins/hallo-hr.js'],
            order=45,
        )
    )
    features.register_converter_rule('editorhtml', 'hr', [
        WhitelistRule('hr', allow_without_attributes)
    ])

    features.register_editor_plugin(
        'hallo', 'link',
        HalloPlugin(
            name='hallowagtaillink',
            js=[
                'wagtailadmin/js/page-chooser-modal.js',
                'wagtailadmin/js/hallo-plugins/hallo-wagtaillink.js',
            ],
        )
    )
    features.register_converter_rule('editorhtml', 'link', [
        WhitelistRule('a', attribute_rule({'href': check_url})),
        LinkTypeRule('page', PageLinkHandler),
    ])

    features.register_editor_plugin(
        'hallo', 'bold', HalloFormatPlugin(format_name='bold')
    )
    features.register_converter_rule('editorhtml', 'bold', [
        WhitelistRule('b', allow_without_attributes),
        WhitelistRule('strong', allow_without_attributes),
    ])

    features.register_editor_plugin(
        'hallo', 'italic', HalloFormatPlugin(format_name='italic')
    )
    features.register_converter_rule('editorhtml', 'italic', [
        WhitelistRule('i', allow_without_attributes),
        WhitelistRule('em', allow_without_attributes),
    ])

    headings_elements = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    headings_order_start = HalloHeadingPlugin.default_order + 1
    for order, element in enumerate(headings_elements, start=headings_order_start):
        features.register_editor_plugin(
            'hallo', element, HalloHeadingPlugin(element=element, order=order)
        )
        features.register_converter_rule('editorhtml', element, [
            WhitelistRule(element, allow_without_attributes)
        ])

    features.register_editor_plugin(
        'hallo', 'ol', HalloListPlugin(list_type='ordered')
    )
    features.register_converter_rule('editorhtml', 'ol', [
        WhitelistRule('ol', allow_without_attributes),
        WhitelistRule('li', allow_without_attributes),
    ])

    features.register_editor_plugin(
        'hallo', 'ul', HalloListPlugin(list_type='unordered')
    )
    features.register_converter_rule('editorhtml', 'ul', [
        WhitelistRule('ul', allow_without_attributes),
        WhitelistRule('li', allow_without_attributes),
    ])

    # Draftail
    features.register_editor_plugin(
        'draftail', 'hr', draftail_features.BooleanFeature('enableHorizontalRule')
    )
    features.register_converter_rule('contentstate', 'hr', {
        'from_database_format': {
            'hr': HorizontalRuleHandler(),
        },
        'to_database_format': {
            'entity_decorators': {'HORIZONTAL_RULE': lambda props: DOM.create_element('hr')}
        }
    })

    features.register_editor_plugin(
        'draftail', 'h1', draftail_features.BlockFeature({
            'label': 'H1',
            'type': 'header-one',
            'description': gettext('Heading %(level)d') % {'level': 1},
        })
    )
    features.register_converter_rule('contentstate', 'h1', {
        'from_database_format': {
            'h1': BlockElementHandler('header-one'),
        },
        'to_database_format': {
            'block_map': {'header-one': 'h1'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'h2', draftail_features.BlockFeature({
            'label': 'H2',
            'type': 'header-two',
            'description': gettext('Heading %(level)d') % {'level': 2},
        })
    )
    features.register_converter_rule('contentstate', 'h2', {
        'from_database_format': {
            'h2': BlockElementHandler('header-two'),
        },
        'to_database_format': {
            'block_map': {'header-two': 'h2'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'h3', draftail_features.BlockFeature({
            'label': 'H3',
            'type': 'header-three',
            'description': gettext('Heading %(level)d') % {'level': 3},
        })
    )
    features.register_converter_rule('contentstate', 'h3', {
        'from_database_format': {
            'h3': BlockElementHandler('header-three'),
        },
        'to_database_format': {
            'block_map': {'header-three': 'h3'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'h4', draftail_features.BlockFeature({
            'label': 'H4',
            'type': 'header-four',
            'description': gettext('Heading %(level)d') % {'level': 4},
        })
    )
    features.register_converter_rule('contentstate', 'h4', {
        'from_database_format': {
            'h4': BlockElementHandler('header-four'),
        },
        'to_database_format': {
            'block_map': {'header-four': 'h4'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'h5', draftail_features.BlockFeature({
            'label': 'H5',
            'type': 'header-five',
            'description': gettext('Heading %(level)d') % {'level': 5},
        })
    )
    features.register_converter_rule('contentstate', 'h5', {
        'from_database_format': {
            'h5': BlockElementHandler('header-five'),
        },
        'to_database_format': {
            'block_map': {'header-five': 'h5'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'h6', draftail_features.BlockFeature({
            'label': 'H6',
            'type': 'header-six',
            'description': gettext('Heading %(level)d') % {'level': 6},
        })
    )
    features.register_converter_rule('contentstate', 'h6', {
        'from_database_format': {
            'h6': BlockElementHandler('header-six'),
        },
        'to_database_format': {
            'block_map': {'header-six': 'h6'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'ul', draftail_features.BlockFeature({
            'type': 'unordered-list-item',
            'icon': 'list-ul',
            'description': gettext('Bulleted list'),
        })
    )
    features.register_converter_rule('contentstate', 'ul', {
        'from_database_format': {
            'ul': ListElementHandler('unordered-list-item'),
            'li': ListItemElementHandler(),
        },
        'to_database_format': {
            'block_map': {'unordered-list-item': {'element': 'li', 'wrapper': 'ul'}}
        }
    })
    features.register_editor_plugin(
        'draftail', 'ol', draftail_features.BlockFeature({
            'type': 'ordered-list-item',
            'icon': 'list-ol',
            'description': gettext('Numbered list'),
        })
    )
    features.register_converter_rule('contentstate', 'ol', {
        'from_database_format': {
            'ol': ListElementHandler('ordered-list-item'),
            'li': ListItemElementHandler(),
        },
        'to_database_format': {
            'block_map': {'ordered-list-item': {'element': 'li', 'wrapper': 'ol'}}
        }
    })
    features.register_editor_plugin(
        'draftail', 'blockquote', draftail_features.BlockFeature({
            'type': 'blockquote',
            'icon': 'openquote',
            'description': gettext('Blockquote'),
        })
    )
    features.register_converter_rule('contentstate', 'blockquote', {
        'from_database_format': {
            'blockquote': BlockElementHandler('blockquote'),
        },
        'to_database_format': {
            'block_map': {'blockquote': 'blockquote'}
        }
    })

    features.register_editor_plugin(
        'draftail', 'bold', draftail_features.InlineStyleFeature({
            'type': 'BOLD',
            'icon': 'bold',
            'description': gettext('Bold'),
        })
    )
    features.register_converter_rule('contentstate', 'bold', {
        'from_database_format': {
            'b': InlineStyleElementHandler('BOLD'),
            'strong': InlineStyleElementHandler('BOLD'),
        },
        'to_database_format': {
            'style_map': {'BOLD': 'b'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'italic', draftail_features.InlineStyleFeature({
            'type': 'ITALIC',
            'icon': 'italic',
            'description': gettext('Italic'),
        })
    )
    features.register_converter_rule('contentstate', 'italic', {
        'from_database_format': {
            'i': InlineStyleElementHandler('ITALIC'),
            'em': InlineStyleElementHandler('ITALIC'),
        },
        'to_database_format': {
            'style_map': {'ITALIC': 'i'}
        }
    })

    features.register_editor_plugin(
        'draftail', 'link', draftail_features.EntityFeature({
            'type': 'LINK',
            'icon': 'link',
            'description': gettext('Link'),
            # We want to enforce constraints on which links can be pasted into rich text.
            # Keep only the attributes Wagtail needs.
            'attributes': ['url', 'id', 'parentId'],
            'whitelist': {
                # Keep pasted links with http/https protocol, and not-pasted links (href = undefined).
                'href': "^(http:|https:|undefined$)",
            }
        }, js=[
            'wagtailadmin/js/page-chooser-modal.js',
        ])
    )
    features.register_converter_rule('contentstate', 'link', {
        'from_database_format': {
            'a[href]': ExternalLinkElementHandler('LINK'),
            'a[linktype="page"]': PageLinkElementHandler('LINK'),
        },
        'to_database_format': {
            'entity_decorators': {'LINK': link_entity}
        }
    })
    features.register_editor_plugin(
        'draftail', 'superscript', draftail_features.InlineStyleFeature({
            'type': 'SUPERSCRIPT',
            'icon': 'superscript',
            'description': gettext('Superscript'),
        })
    )
    features.register_converter_rule('contentstate', 'superscript', {
        'from_database_format': {
            'sup': InlineStyleElementHandler('SUPERSCRIPT'),
        },
        'to_database_format': {
            'style_map': {'SUPERSCRIPT': 'sup'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'subscript', draftail_features.InlineStyleFeature({
            'type': 'SUBSCRIPT',
            'icon': 'subscript',
            'description': gettext('Subscript'),
        })
    )
    features.register_converter_rule('contentstate', 'subscript', {
        'from_database_format': {
            'sub': InlineStyleElementHandler('SUBSCRIPT'),
        },
        'to_database_format': {
            'style_map': {'SUBSCRIPT': 'sub'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'strikethrough', draftail_features.InlineStyleFeature({
            'type': 'STRIKETHROUGH',
            'icon': 'strikethrough',
            'description': gettext('Strikethrough'),
        })
    )
    features.register_converter_rule('contentstate', 'strikethrough', {
        'from_database_format': {
            's': InlineStyleElementHandler('STRIKETHROUGH'),
        },
        'to_database_format': {
            'style_map': {'STRIKETHROUGH': 's'}
        }
    })
    features.register_editor_plugin(
        'draftail', 'code', draftail_features.InlineStyleFeature({
            'type': 'CODE',
            'icon': 'code',
            'description': gettext('Code'),
        })
    )
    features.register_converter_rule('contentstate', 'code', {
        'from_database_format': {
            'code': InlineStyleElementHandler('CODE'),
        },
        'to_database_format': {
            'style_map': {'CODE': 'code'}
        }
    })


class ReportsMenuItem(SubmenuMenuItem):
    template = 'wagtailadmin/shared/menu_submenu_item.html'


class LockedPagesMenuItem(MenuItem):
    def is_shown(self, request):
        return UserPagePermissionsProxy(request.user).can_remove_locks()


class WorkflowReportMenuItem(MenuItem):
    def is_shown(self, request):
        return True


class SiteHistoryReportMenuItem(MenuItem):
    def is_shown(self, request):
        return UserPagePermissionsProxy(request.user).explorable_pages().exists()


@hooks.register('register_reports_menu_item')
def register_locked_pages_menu_item():
    return LockedPagesMenuItem(_('Locked Pages'), reverse('wagtailadmin_reports:locked_pages'), icon_name='lock', order=700)


@hooks.register('register_reports_menu_item')
def register_workflow_report_menu_item():
    return WorkflowReportMenuItem(_('Workflows'), reverse('wagtailadmin_reports:workflow'), icon_name='tasks', order=800)


@hooks.register('register_reports_menu_item')
def register_workflow_tasks_report_menu_item():
    return WorkflowReportMenuItem(_('Workflow tasks'), reverse('wagtailadmin_reports:workflow_tasks'), icon_name='thumbtack', order=900)


@hooks.register('register_reports_menu_item')
def register_site_history_report_menu_item():
    return SiteHistoryReportMenuItem(_('Site history'), reverse('wagtailadmin_reports:site_history'), icon_name='history', order=1000)


@hooks.register('register_admin_menu_item')
def register_reports_menu():
    return ReportsMenuItem(
        _('Reports'), reports_menu, icon_name='site', order=9000)


@hooks.register('register_icons')
def register_icons(icons):
    for icon in [
        'arrow-down-big.svg',
        'arrow-down.svg',
        'arrow-left.svg',
        'arrow-right.svg',
        'arrow-up-big.svg',
        'arrow-up.svg',
        'arrows-up-down.svg',
        'bin.svg',
        'bold.svg',
        'chain-broken.svg',
        'clipboard-list.svg',
        'code.svg',
        'cog.svg',
        'cogs.svg',
        'collapse-down.svg',
        'collapse-up.svg',
        'cross.svg',
        'date.svg',
        'doc-empty-inverse.svg',
        'doc-empty.svg',
        'doc-full-inverse.svg',
        'doc-full.svg',  # aka file-text-alt
        'download-alt.svg',
        'download.svg',
        'draft.svg',
        'duplicate.svg',
        'edit.svg',
        'error.svg',
        'folder-inverse.svg',
        'folder-open-1.svg',
        'folder-open-inverse.svg',
        'folder.svg',
        'form.svg',
        'grip.svg',
        'group.svg',
        'help.svg',
        'history.svg',
        'home.svg',
        'horizontalrule.svg',
        'image.svg',  # aka picture
        'italic.svg',
        'link.svg',
        'link-external.svg',
        'list-ol.svg',
        'list-ul.svg',
        'lock-open.svg',
        'lock.svg',
        'login.svg',
        'logout.svg',
        'mail.svg',
        'media.svg',
        'no-view.svg',
        'openquote.svg',
        'order-down.svg',
        'order-up.svg',
        'order.svg',
        'password.svg',
        'pick.svg',
        'pilcrow.svg',
        'placeholder.svg',  # aka marquee
        'plus-inverse.svg',
        'plus.svg',
        'radio-empty.svg',
        'radio-full.svg',
        'redirect.svg',
        'repeat.svg',
        'reset.svg',
        'resubmit.svg',
        'search.svg',
        'site.svg',
        'snippet.svg',
        'spinner.svg',
        'strikethrough.svg',
        'success.svg',
        'subscript.svg',
        'superscript.svg',
        'table.svg',
        'tag.svg',
        'tasks.svg',
        'thumbtack.svg',
        'tick-inverse.svg',
        'tick.svg',
        'time.svg',
        'title.svg',
        'undo.svg',
        'uni52.svg',  # Is this a redundant icon?
        'upload.svg',
        'user.svg',
        'view.svg',
        'wagtail-inverse.svg',
        'wagtail.svg',
        'warning.svg',
    ]:
        icons.append('wagtailadmin/icons/{}'.format(icon))
    return icons


@hooks.register('construct_homepage_summary_items')
def add_pages_summary_item(request, items):
    items.insert(0, PagesSummaryItem(request))


@hooks.register('register_log_actions')
def register_core_log_actions(actions):
    actions.register_action('wagtail.create', _('Create'), _('Created'))
    actions.register_action('wagtail.edit', _('Save draft'), _('Draft saved'))
    actions.register_action('wagtail.delete', _('Delete'), _('Deleted'))
    actions.register_action('wagtail.publish', _('Publish'), _('Published'))
    actions.register_action('wagtail.publish.scheduled', _("Publish scheduled draft"), _('Published scheduled draft'))
    actions.register_action('wagtail.unpublish', _('Unpublish'), _('Unpublished'))
    actions.register_action('wagtail.unpublish.scheduled', _('Unpublish scheduled draft'), _('Unpublished scheduled draft'))
    actions.register_action('wagtail.lock', _('Lock'), _('Locked'))
    actions.register_action('wagtail.unlock', _('Unlock'), _('Unlocked'))
    actions.register_action('wagtail.moderation.approve', _('Approve'), _('Approved'))
    actions.register_action('wagtail.moderation.reject', _('Reject'), _('Rejected'))

    def revert_message(data):
        try:
            return _('Reverted to previous revision with id %(revision_id)s from %(created_at)s') % {
                'revision_id': data['revision']['id'],
                'created_at': data['revision']['created'],
            }
        except KeyError:
            return _('Reverted to previous revision')

    def copy_message(data):
        try:
            return _('Copied from %(title)s') % {
                'title': data['source']['title'],
            }
        except KeyError:
            return _("Copied")

    def create_alias_message(data):
        try:
            return _('Created an alias of %(title)s') % {
                'title': data['source']['title'],
            }
        except KeyError:
            return _("Created an alias")

    def convert_alias_message(data):
        try:
            return _("Converted the alias '%(title)s' into a regular page") % {
                'title': data['page']['title'],
            }
        except KeyError:
            return _("Converted an alias into a regular page")

    def move_message(data):
        try:
            return _("Moved from '%(old_parent)s' to '%(new_parent)s'") % {
                'old_parent': data['source']['title'],
                'new_parent': data['destination']['title'],
            }
        except KeyError:
            return _('Moved')

    def schedule_publish_message(data):
        try:
            if data['revision']['has_live_version']:
                return _('Revision %(revision_id)s from %(created_at)s scheduled for publishing at %(go_live_at)s.') % {
                    'revision_id': data['revision']['id'],
                    'created_at': data['revision']['created'],
                    'go_live_at': data['revision']['go_live_at'],
                }
            else:
                return _('Page scheduled for publishing at %(go_live_at)s') % {
                    'go_live_at': data['revision']['go_live_at'],
                }
        except KeyError:
            return _('Page scheduled for publishing')

    def unschedule_publish_message(data):
        try:
            if data['revision']['has_live_version']:
                return _('Revision %(revision_id)s from %(created_at)s unscheduled from publishing at %(go_live_at)s.') % {
                    'revision_id': data['revision']['id'],
                    'created_at': data['revision']['created'],
                    'go_live_at': data['revision']['go_live_at'],
                }
            else:
                return _('Page unscheduled for publishing at %(go_live_at)s') % {
                    'go_live_at': data['revision']['go_live_at'],
                }
        except KeyError:
            return _('Page unscheduled from publishing')

    def add_view_restriction(data):
        try:
            return _("Added the '%(restriction)s' view restriction") % {
                'restriction': data['restriction']['title'],
            }
        except KeyError:
            return _('Added view restriction')

    def edit_view_restriction(data):
        try:
            return _("Updated the view restriction to '%(restriction)s'") % {
                'restriction': data['restriction']['title'],
            }
        except KeyError:
            return _('Updated view restriction')

    def delete_view_restriction(data):
        try:
            return _("Removed the '%(restriction)s' view restriction") % {
                'restriction': data['restriction']['title'],
            }
        except KeyError:
            return _('Removed view restriction')

    def rename_message(data):
        try:
            return _("Renamed from '%(old)s' to '%(new)s'") % {
                'old': data['title']['old'],
                'new': data['title']['new'],
            }
        except KeyError:
            return _('Renamed')

    actions.register_action('wagtail.rename', _('Rename'), rename_message)
    actions.register_action('wagtail.revert', _('Revert'), revert_message)
    actions.register_action('wagtail.copy', _('Copy'), copy_message)
    actions.register_action('wagtail.create_alias', _('Create alias'), create_alias_message)
    actions.register_action('wagtail.convert_alias', _('Convert alias into regular page'), convert_alias_message)
    actions.register_action('wagtail.move', _('Move'), move_message)
    actions.register_action('wagtail.publish.schedule', _("Schedule publication"), schedule_publish_message)
    actions.register_action('wagtail.schedule.cancel', _("Unschedule publication"), unschedule_publish_message)
    actions.register_action('wagtail.view_restriction.create', _("Add view restrictions"), add_view_restriction)
    actions.register_action('wagtail.view_restriction.edit', _("Update view restrictions"), edit_view_restriction)
    actions.register_action('wagtail.view_restriction.delete', _("Remove view restrictions"), delete_view_restriction)


@hooks.register('register_log_actions')
def register_workflow_log_actions(actions):
    def workflow_start_message(data):
        try:
            return _("'%(workflow)s' started. Next step '%(task)s'") % {
                'workflow': data['workflow']['title'],
                'task': data['workflow']['next']['title'],
            }
        except (KeyError, TypeError):
            return _('Workflow started')

    def workflow_approve_message(data):
        try:
            if data['workflow']['next']:
                return _("Approved at '%(task)s'. Next step '%(next_task)s'") % {
                    'task': data['workflow']['task']['title'],
                    'next_task': data['workflow']['next']['title'],
                }
            else:
                return _("Approved at '%(task)s'. '%(workflow)s' complete") % {
                    'task': data['workflow']['task']['title'],
                    'workflow': data['workflow']['title'],
                }
        except (KeyError, TypeError):
            return _('Workflow task approved')

    def workflow_reject_message(data):
        try:
            return _("Rejected at '%(task)s'. Changes requested") % {
                'task': data['workflow']['task']['title'],
            }
        except (KeyError, TypeError):
            return _('Workflow task rejected. Workflow complete')

    def workflow_resume_message(data):
        try:
            return _("Resubmitted '%(task)s'. Workflow resumed'") % {
                'task': data['workflow']['task']['title'],
            }
        except (KeyError, TypeError):
            return _('Workflow task resubmitted. Workflow resumed')

    def workflow_cancel_message(data):
        try:
            return _("Cancelled '%(workflow)s' at '%(task)s'") % {
                'workflow': data['workflow']['title'],
                'task': data['workflow']['task']['title'],
            }
        except (KeyError, TypeError):
            return _('Workflow cancelled')

    actions.register_action('wagtail.workflow.start', _('Workflow: start'), workflow_start_message)
    actions.register_action('wagtail.workflow.approve', _('Workflow: approve task'), workflow_approve_message)
    actions.register_action('wagtail.workflow.reject', _('Workflow: reject task'), workflow_reject_message)
    actions.register_action('wagtail.workflow.resume', _('Workflow: resume task'), workflow_resume_message)
    actions.register_action('wagtail.workflow.cancel', _('Workflow: cancel'), workflow_cancel_message)
