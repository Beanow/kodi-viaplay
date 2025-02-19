import urllib
import sys

if sys.version_info[0] > 2:
    from .viaplay import Viaplay
else:
    from viaplay import Viaplay

import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
import inputstreamhelper
from xbmcaddon import Addon


class KodiHelper(object):
    def __init__(self, base_url=None, handle=None):
        addon = self.get_addon()
        self.base_url = base_url
        self.handle = handle
        if sys.version_info[0] > 2:
            self.addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
            self.addon_profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        else:
            self.addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
            self.addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
        self.addon_name = addon.getAddonInfo('id')
        self.addon_version = addon.getAddonInfo('version')
        self.language = addon.getLocalizedString
        self.logging_prefix = '[%s-%s]' % (self.addon_name, self.addon_version)
        if not xbmcvfs.exists(self.addon_profile):
            xbmcvfs.mkdir(self.addon_profile)
        if self.get_setting('first_run'):
            self.get_addon().openSettings()
            self.set_setting('first_run', 'false')
        self.vp = Viaplay(self.addon_profile, self.get_country_code(), True)

    def get_addon(self):
        """Returns a fresh addon instance."""
        return Addon()

    def get_setting(self, setting_id):
        addon = self.get_addon()
        setting = addon.getSetting(setting_id)
        if setting == 'true':
            return True
        elif setting == 'false':
            return False
        else:
            return setting

    def set_setting(self, key, value):
        return self.get_addon().setSetting(key, value)

    def log(self, string):
        msg = '%s: %s' % (self.logging_prefix, string)
        xbmc.log(msg=msg, level=xbmc.LOGDEBUG)

    def get_country_code(self):
        country_id = self.get_setting('site')
        if country_id == '0':
            country_code = 'se'
        elif country_id == '1':
            country_code = 'dk'
        elif country_id == '2':
            country_code = 'no'
        elif country_id == '3':
            country_code = 'fi'
        elif country_id == '4':
            country_code = 'pl'
        elif country_id == '5':
            country_code = 'lt'

        return country_code

    def dialog(self, dialog_type, heading, message=None, options=None, nolabel=None, yeslabel=None):
        dialog = xbmcgui.Dialog()
        if dialog_type == 'ok':
            dialog.ok(heading, message)
        elif dialog_type == 'yesno':
            return dialog.yesno(heading, message, nolabel=nolabel, yeslabel=yeslabel)
        elif dialog_type == 'select':
            ret = dialog.select(heading, options)
            if ret > -1:
                return ret
            else:
                return None
        elif dialog_type == 'multiselect':
            ret = dialog.multiselect(heading, options)
            if ret:
                return ret
            else:
                return None
        elif dialog_type == 'notification':
            dialog.notification(heading, message)

    def log_out(self):
        confirm = self.dialog('yesno', self.language(30042), self.language(30043))
        if confirm:
            self.vp.log_out()

    def authorize(self):
        if xbmc.getCondVisibility('!Window.IsVisible(Home)'):
            try:
                self.vp.validate_session()
                return True
            except self.vp.ViaplayError as error:
                cookie_error = 'MissingSessionCookieError'
                login_error = 'PersistentLoginError'

                if not error.value == login_error or error.value == cookie_error:
                    raise
                else:
                    return self.device_registration()

    def device_registration(self):
        """Presents a dialog with information on how to activate the device.
        Attempts to authorize the device using the interval returned by the activation data."""
        activation_data = self.vp.get_activation_data()
        message = self.language(30039).format(activation_data['verificationUrl'], activation_data['userCode'])
        dialog = xbmcgui.DialogProgress()
        xbmc.sleep(200)  # small delay to prevent DialogProgress from hanging
        dialog.create(self.language(30040), message)
        secs = 0
        expires = activation_data['expires']

        while not xbmc.Monitor().abortRequested() and secs < expires:
            try:
                self.vp.authorize_device(activation_data)
                dialog.close()
                return True
            except self.vp.ViaplayError as error:
                # raise all non-pending authorization errors
                auth_error = 'DeviceAuthorizationPendingError'
                dev_error = 'DeviceAuthorizationNotFound'

                if error.value == auth_error:
                    secs += activation_data['interval']
                    percent = int(100 * float(secs) / float(expires))
                    dialog.update(percent, message)
                    xbmc.Monitor().waitForAbort(activation_data['interval'])
                    if dialog.iscanceled():
                        dialog.close()
                        return False
                elif error.value == dev_error:  # time expired
                    dialog.close()
                    self.dialog('ok', self.language(30051), self.language(30052))
                    return False
                else:
                    dialog.close()
                    raise

        dialog.close()
        return False

    def get_user_input(self, heading, hidden=False):
        keyboard = xbmc.Keyboard('', heading, hidden)
        keyboard.doModal()
        if keyboard.isConfirmed():
            query = keyboard.getText()
            self.log('User input string: %s' % query)
        else:
            query = None

        if query and len(query) > 0:
            return query
        else:
            return None

    def get_numeric_input(self, heading):
        dialog = xbmcgui.Dialog()
        numeric_input = dialog.numeric(0, heading)

        if len(numeric_input) > 0:
            return str(numeric_input)
        else:
            return None

    def add_item(self, title, url, folder=True, playable=False, info=None, art=None, content=False, episode=False):
        addon = self.get_addon()
        listitem = xbmcgui.ListItem(label=title)

        if playable:
            listitem.setProperty('IsPlayable', 'true')
            folder = False
        if art:
            listitem.setArt(art)
        else:
            art = {
                'icon': addon.getAddonInfo('icon'),
                'fanart': addon.getAddonInfo('fanart')
            }
            listitem.setArt(art)
        if info:
            listitem.setInfo('Video', info)
        if content:
            xbmcplugin.setContent(self.handle, content)

        xbmcplugin.addDirectoryItem(self.handle, url, listitem, folder)

        if episode:
            xbmcplugin.addSortMethod(handle=self.handle, sortMethod=xbmcplugin.SORT_METHOD_EPISODE)

    def eod(self):
        """Tell Kodi that the end of the directory listing is reached."""
        xbmcplugin.endOfDirectory(self.handle, cacheToDisc=False)

    def play(self, guid=None, url=None, pincode=None, tve='false'):
        if url and url != 'None':
            guid = self.vp.get_products(url)['products'][0]['system']['guid']
        
        try:
            stream = self.vp.get_stream(guid, pincode=pincode, tve=tve)
        
        except self.vp.ViaplayError as error:
            if error.value == 'MissingVideoError':
                message = 'Content is missing'
                self.dialog(dialog_type='notification', heading=self.language(30017), message=message)
                return

            elif error.value == 'AnonymousProxyError':
                message = 'This content is not available via an anonymous proxy'
                self.dialog(dialog_type='notification', heading=self.language(30017), message=message)
                return

            elif error.value == 'ParentalGuidancePinChallengeNeededError':
                self.authorize()
                return

            if error.value == 'ParentalGuidancePinChallengeNeededError':
                if pincode:
                    self.dialog(dialog_type='ok', heading=self.language(30033), message=self.language(30034))
                else:
                    pincode = self.get_numeric_input(self.language(30032))
                    if pincode:
                        self.play(guid, pincode=pincode)
                    return
            else:
                raise

        ia_helper = inputstreamhelper.Helper('mpd', drm='widevine')
        if ia_helper.check_inputstream():
            playitem = xbmcgui.ListItem(path=stream['mpd_url'])
            playitem.setContentLookup(False)
            playitem.setMimeType('application/xml+dash')  # prevents HEAD request that causes 404 error
            if sys.version_info[0] > 2:
                playitem.setProperty('inputstream', 'inputstream.adaptive')
            else:    
                playitem.setProperty('inputstreamaddon', 'inputstream.adaptive')
            playitem.setProperty('inputstream.adaptive.manifest_type', 'mpd')
            playitem.setProperty('inputstream.adaptive.manifest_update_parameter', 'full')
            playitem.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
            playitem.setProperty('inputstream.adaptive.license_key',stream['license_url'].replace('{widevineChallenge}', 'B{SSM}') + '|||JBlicense')
            if self.get_setting('subtitles') and 'subtitles' in stream:
                playitem.setSubtitles(self.vp.download_subtitles(stream['subtitles']))
            xbmcplugin.setResolvedUrl(self.handle, True, listitem=playitem)

    def ia_settings(self):
        """Open InputStream Adaptive settings."""
        ia_addon = Addon('inputstream.adaptive')
        ia_addon.openSettings()
