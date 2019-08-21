import django.contrib.auth
import django.http
import django.shortcuts
import django.urls
import django.utils.decorators
import django.views.decorators.csrf
import django.views.generic
import django.views.generic.base

import json
import re

import app.core
import app.forms
import app.models


allowedIps = ['localhost', '127.0.0.1', '188.242.232.131']
def allow_by_ip(view_func):
    def authorize(request, *args, **kwargs):
        user_ip = request.META['REMOTE_ADDR']
        if user_ip in allowedIps:
            return view_func(request, *args, **kwargs)
        # TODO: 403 Error
        return django.http.HttpResponse('Invalid Ip Access!')
    return authorize


@allow_by_ip
def login(request):
    if request.POST.get('login'):
        user_login = request.POST.get('username')
        user_password = request.POST.get('password')
        user = django.contrib.auth.authenticate(username=user_login, password=user_password)

        response_data = {}
        if user:
            django.contrib.auth.login(request, user)
            response_data['result'] = 'Success!'
        else:
            response_data['result'] = 'Failed!'
        return django.http.HttpResponse(json.dumps(response_data), content_type="application/json")

    return django.shortcuts.render(request, 'login.html')


class FilemanagerMixin(object):
    def dispatch(self, request, *args, **kwargs):
        params = dict(request.GET)
        params.update(dict(request.POST))

        self.fm = app.core.Filemanager()
        if 'path' in params and len(params['path'][0]) > 0:
            self.fm.update_path(params['path'][0])
        if 'popup' in params:
            self.popup = params['popup']

        return super(FilemanagerMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super(FilemanagerMixin, self).get_context_data(*args, **kwargs)

        self.fm.patch_context_data(context)

        if hasattr(self, 'popup'):
            context['popup'] = self.popup

        if hasattr(self, 'extra_breadcrumbs') and isinstance(self.extra_breadcrumbs, list):
            context['breadcrumbs'] += self.extra_breadcrumbs

        return context


class JSONResponseMixin:
    """
    A mixin that can be used to render a JSON response.
    """
    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        response_kwargs['content_type']='application/javascript; charset=utf8'
        return django.http.JsonResponse(
            self.get_data(context),
            **response_kwargs
        )

    def get_data(self, context):
        """
        Returns an object that will be serialized as JSON by json.dumps().
        """
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return context


class BrowserView(FilemanagerMixin, django.views.generic.TemplateView):
    template_name = 'filemanager/browser/filemanager_list.html'

    def dispatch(self, request, *args, **kwargs):
        self.popup = self.request.GET.get('popup', 0) == '1'
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['popup'] = self.popup

        query = self.request.GET.get('q')
        search_params = self.request.GET.get('search_param')

        if query:
            if(re.match('here', search_params, re.I)):
                files = self.fm.directory_list()

                q = []
                for file in files:
                    if re.search(query, file['filename'], re.I):
                        q.append(file)
                    try:
                        if file['filetype'] == 'File':
                            with open('media/uploads/'+file['filepath']) as f:
                                content = f.read()
                                if query in content:
                                    q.append(file)
                    except:
                        pass

                context['files'] = q
                context['empty'] = 'No item found'

            else:
                context['files'] = self.fm.search(query)
                context['empty'] = 'No item found'

        else:
            context['files'] = self.fm.directory_list()
            context['empty'] = 'Folder is empty'

        return context


class DetailView(FilemanagerMixin, JSONResponseMixin, django.views.generic.TemplateView, django.views.generic.detail.SingleObjectTemplateResponseMixin):
    template_name = 'filemanager/browser/filemanager_detail.html'

    # def get_context_data(self, **kwargs):
    #     context = super(DetailView, self).get_context_data(**kwargs)
    #
    #     context['file'] = self.fm.file_details()
    #
    #     return context

    def render_to_response(self, context, **response_kwargs):
        context['file'] = self.fm.file_details()
        if self.request.GET.get('format') == 'json':
            return self.render_to_json_response(context['file'])
        else:
            return super().render_to_response(context)

    # def get(self, request, *args, **kwargs):
    #
    #     return django.http.JsonResponse({'data':'james'})


class UploadView(FilemanagerMixin, django.views.generic.TemplateView):
    template_name = 'filemanager/filemanager_upload.html'
    extra_breadcrumbs = [{
        'path': '#',
        'label': 'Upload'
    }]


class UploadFileView(FilemanagerMixin, django.views.generic.base.View):
    def post(self, request, *args, **kwargs):

        # TODO: get filepath and validate characters in name, validate mime type and extension
        filename = self.fm.upload_file(request.POST['rel_path'], request.FILES['files[]'])

        return django.shortcuts.HttpResponse(json.dumps({
            'files': [{'name': filename}],
        }))


class DirectoryCreateView(FilemanagerMixin, django.views.generic.FormView):
    template_name = 'filemanager/filemanager_create_directory.html'
    form_class = app.forms.DirectoryCreateForm
    extra_breadcrumbs = [{
        'path': '#',
        'label': 'Create directory'
    }]

    def get_success_url(self):
        url = '%s?path=%s' % (django.shortcuts.reverse('browser'), self.fm.path)
        if hasattr(self, 'popup') and self.popup:
            url += '&popup=1'
        return url

    def form_valid(self, form):
        self.fm.create_directory(form.cleaned_data.get('directory_name'))
        return super(DirectoryCreateView, self).form_valid(form)


class RenameView(FilemanagerMixin, django.views.generic.FormView):
    template_name = 'filemanager/rename_modal.html'
    form_class = app.forms.RenameForm
    extra_breadcrumbs = [{
        'path': '#',
        'label': 'Rename'
    }]

    def get_success_url(self):
        url = '%s?path=%s' % (django.shortcuts.reverse('browser'), self.fm.path)
        if hasattr(self, 'popup') and self.popup:
            url += '&popup=1'
        return url

    def form_valid(self, form):
        self.fm.rename(form.cleaned_data.get('old_name'), form.cleaned_data.get('input_name'))

        return super(RenameView, self).form_valid(form)


class DeleteView(FilemanagerMixin, django.views.generic.base.View):

    @django.utils.decorators.method_decorator(django.views.decorators.csrf.csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(DeleteView, self).dispatch(request, *args, **kwargs)

    def post(self, request):
        json_data = json.loads(request.body)
        try:
            for files in json_data['files']:
                self.fm.remove(files)

        except Exception as e:
            print(e)
        return django.shortcuts.HttpResponse('success')


class ReplaceView(FilemanagerMixin, django.views.generic.FormView):
    template_name = 'filemanager/replace_modal.html'
    form_class = app.forms.ReplaceForm
    extra_breadcrumbs = [{
        'path': '#',
        'label': 'Replace'
    }]

    def get_success_url(self):
        url = '%s?path=%s' % (django.shortcuts.reverse('browser'), self.fm.path)
        if hasattr(self, 'popup') and self.popup:
            url += '&popup=1'
        return url

    def form_valid(self, form):
        self.fm.replace(form.cleaned_data.get('old_path'), form.cleaned_data.get('input_path'))
        return super(ReplaceView, self).form_valid(form)


class BlockView(FilemanagerMixin, django.views.generic.ListView):
    def post(self, request):
        self.fm.block(request.POST['path'])
        return django.shortcuts.HttpResponse('success')


class UnblockView(FilemanagerMixin, django.views.generic.ListView):
    def post(self, request):
        self.fm.unblock(request.POST['path'])
        return django.shortcuts.HttpResponse('success')


class AccessUrlView(FilemanagerMixin, django.views.generic.ListView):
    def post(self, request):
        self.fm.access_url(request.POST['path'])
        return django.shortcuts.HttpResponse('success')


class UnaccessUrlView(FilemanagerMixin, django.views.generic.ListView):
    def post(self, request):
        self.fm.unaccess_url(request.POST['path'])
        return django.shortcuts.HttpResponse('success')


class SaveUrlView(FilemanagerMixin, django.views.generic.ListView):
    def post(self, request):
        self.fm.save_url(request.POST['path'], request.POST.getlist('urls[]'))
        return django.shortcuts.HttpResponse('success')
