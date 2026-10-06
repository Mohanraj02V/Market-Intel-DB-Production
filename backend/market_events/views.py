from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Prefetch
from .models import MarketEvent, MarketEventParticipation
from .serializers import MarketEventSerializer
from .permissions import MarketEventPermission

class MarketEventViewSet(viewsets.ModelViewSet):
    serializer_class = MarketEventSerializer
    permission_classes = [MarketEventPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['host_country']
    search_fields = ['event_title', 'host_country']
    ordering_fields = ['start_date', 'end_date', 'event_title', 'created_at']
    ordering = ['-start_date']

    def get_queryset(self):
        user = self.request.user
        
        # Build a Q object to filter the Count based on user role
        from django.db.models import Q
        count_filter = Q()
        
        if not user.is_superuser and hasattr(user, 'profile'):
            role = user.profile.role
            if role == 'PRE':
                count_filter &= Q(participations__prospect__created_by=user.username)
            elif role == 'LQ':
                # LQ sees only prospects assigned to them
                # apply_lq_distribution_filter uses lead_qualification__assigned_lq
                count_filter &= Q(participations__prospect__lead_qualification__assigned_lq=user)

        # Always annotate with the count of participating companies, filtered by role
        queryset = MarketEvent.objects.annotate(
            participating_companies_count=Count('participations', filter=count_filter, distinct=True)
        )
        
        # If it's a detail view, prefetch the participating prospects to avoid N+1
        if self.action == 'retrieve':
            participations_qs = MarketEventParticipation.objects.select_related('prospect')
            if not user.is_superuser and hasattr(user, 'profile'):
                role = user.profile.role
                if role == 'PRE':
                    participations_qs = participations_qs.filter(prospect__created_by=user.username)
                elif role == 'LQ':
                    participations_qs = participations_qs.filter(prospect__lead_qualification__assigned_lq=user)

            prefetch = Prefetch(
                'participations',
                queryset=participations_qs,
                to_attr='prefetched_participations'
            )
            queryset = queryset.prefetch_related(prefetch)
            
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user.username)

    def perform_destroy(self, instance):
        # Constraints ensure cascade delete handles participation records safely
        instance.delete()
