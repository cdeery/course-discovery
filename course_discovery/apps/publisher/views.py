"""
Course publisher views.
"""
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic.list import ListView
from django_fsm import TransitionNotAllowed
from guardian.shortcuts import get_objects_for_user

from course_discovery.apps.publisher.forms import CourseForm, CourseRunForm, SeatForm
from course_discovery.apps.publisher import mixins
from course_discovery.apps.publisher.models import Course, CourseRun, Seat, State
from course_discovery.apps.publisher.wrappers import CourseRunWrapper


SEATS_HIDDEN_FIELDS = ['price', 'currency', 'upgrade_deadline', 'credit_provider', 'credit_hours']


class CourseRunListView(mixins.LoginRequiredMixin, ListView):
    """ Create Course View."""
    template_name = 'publisher/course_runs_list.html'

    def get_queryset(self):
        if self.request.user.is_staff:
            course_runs = CourseRun.objects.select_related('course').all()
        else:
            courses = get_objects_for_user(self.request.user, Course.VIEW_PERMISSION, Course)
            course_runs = CourseRun.objects.filter(course__in=courses).select_related('course').all()

        return course_runs

    def get_context_data(self, **kwargs):
        context = super(CourseRunListView, self).get_context_data(**kwargs)
        course_runs = context.get('object_list')
        published_courseruns = course_runs.filter(
            state__name=State.PUBLISHED
        ).select_related('course').all().order_by('-state__modified')[:5]
        unpublished_courseruns = course_runs.exclude(state__name=State.PUBLISHED)
        context['object_list'] = [CourseRunWrapper(course_run) for course_run in unpublished_courseruns]
        context['published_courseruns'] = [CourseRunWrapper(course_run) for course_run in published_courseruns]
        return context


class CourseRunDetailView(mixins.LoginRequiredMixin, mixins.ViewPermissionMixin, DetailView):
    """ Course Run Detail View."""
    model = CourseRun
    template_name = 'publisher/course_run_detail.html'

    def get_context_data(self, **kwargs):
        context = super(CourseRunDetailView, self).get_context_data(**kwargs)
        context['object'] = CourseRunWrapper(context['object'])
        context['comment_object'] = self.object.course
        return context


# pylint: disable=attribute-defined-outside-init
class CreateCourseView(mixins.LoginRequiredMixin, mixins.FormValidMixin, CreateView):
    """ Create Course View."""
    model = Course
    form_class = CourseForm
    template_name = 'publisher/course_form.html'
    success_url = 'publisher:publisher_courses_edit'
    assign_user_groups = True

    def get_success_url(self):
        return reverse(self.success_url, kwargs={'pk': self.object.id})


class UpdateCourseView(mixins.LoginRequiredMixin, mixins.ViewPermissionMixin, mixins.FormValidMixin, UpdateView):
    """ Update Course View."""
    model = Course
    form_class = CourseForm
    permission_required = Course.VIEW_PERMISSION
    template_name = 'publisher/course_form.html'
    success_url = 'publisher:publisher_courses_edit'

    def get_success_url(self):
        return reverse(self.success_url, kwargs={'pk': self.object.id})

    def get_context_data(self, **kwargs):
        context = super(UpdateCourseView, self).get_context_data(**kwargs)
        context['comment_object'] = self.object
        return context


class CreateCourseRunView(mixins.LoginRequiredMixin, mixins.FormValidMixin, CreateView):
    """ Create Course Run View."""
    model = CourseRun
    form_class = CourseRunForm
    template_name = 'publisher/course_run_form.html'
    success_url = 'publisher:publisher_course_runs_edit'

    def get_success_url(self):
        return reverse(self.success_url, kwargs={'pk': self.object.id})


class UpdateCourseRunView(mixins.LoginRequiredMixin, mixins.ViewPermissionMixin, mixins.FormValidMixin, UpdateView):
    """ Update Course Run View."""
    model = CourseRun
    form_class = CourseRunForm
    permission_required = Course.VIEW_PERMISSION
    template_name = 'publisher/course_run_form.html'
    success_url = 'publisher:publisher_course_runs_edit'
    change_state = True

    def get_context_data(self, **kwargs):
        context = super(UpdateCourseRunView, self).get_context_data(**kwargs)
        if not self.object:
            self.object = self.get_object()
        context['workflow_state'] = self.object.current_state
        context['comment_object'] = self.object
        return context

    def get_success_url(self):
        return reverse(self.success_url, kwargs={'pk': self.object.id})


class CreateSeatView(mixins.LoginRequiredMixin, mixins.FormValidMixin, CreateView):
    """ Create Seat View."""
    model = Seat
    form_class = SeatForm
    template_name = 'publisher/seat_form.html'
    success_url = 'publisher:publisher_seats_edit'

    def get_context_data(self, **kwargs):
        context = super(CreateSeatView, self).get_context_data(**kwargs)
        context['hidden_fields'] = SEATS_HIDDEN_FIELDS
        return context

    def get_success_url(self):
        return reverse(self.success_url, kwargs={'pk': self.object.id})


class UpdateSeatView(mixins.LoginRequiredMixin, mixins.ViewPermissionMixin, mixins.FormValidMixin, UpdateView):
    """ Update Seat View."""
    model = Seat
    form_class = SeatForm
    permission_required = Course.VIEW_PERMISSION
    template_name = 'publisher/seat_form.html'
    success_url = 'publisher:publisher_seats_edit'

    def get_context_data(self, **kwargs):
        context = super(UpdateSeatView, self).get_context_data(**kwargs)
        context['hidden_fields'] = SEATS_HIDDEN_FIELDS
        context['comment_object'] = self.object
        return context

    def get_success_url(self):
        return reverse(self.success_url, kwargs={'pk': self.object.id})


class ChangeStateView(mixins.LoginRequiredMixin, View):
    """ Change Workflow State View"""

    def post(self, request, course_run_id):
        state = request.POST.get('state')
        try:
            course_run = CourseRun.objects.get(id=course_run_id)

            if not mixins.check_view_permission(request.user, course_run.course):
                return HttpResponseForbidden()

            course_run.change_state(target=state, user=self.request.user)
            # pylint: disable=no-member
            messages.success(
                request, _('Content moved to `{state}` successfully.').format(state=course_run.current_state)
            )
            return HttpResponseRedirect(reverse('publisher:publisher_course_run_detail', kwargs={'pk': course_run_id}))
        except (CourseRun.DoesNotExist, TransitionNotAllowed):
            messages.error(request, _('There was an error in changing state.'))
            return HttpResponseRedirect(reverse('publisher:publisher_course_run_detail', kwargs={'pk': course_run_id}))
