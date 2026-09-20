var Dargah = angular.module('Contracts', ['ui.router']);

Dargah.config(function ($stateProvider, $urlRouterProvider) {
    $urlRouterProvider.otherwise('/Contract/Index');
    $stateProvider
        .state('Contract', {
            templateUrl: '/Contract/Index',
            controller: 'ContractController',
            url: '/Contract/Index'
        })
        .state('ContractSign', {
            templateUrl: '/Contract/Sign',
            controller: 'ContractSignController',
            url: '/Contract/Sign'
        });
});

Dargah.controller('ContractController', function ($scope, $http, $resource) {
    $scope.model = {};
    $scope.save = function () {
        $http.post('/Contract/GetContractSignContext', { contractID: $scope.id });
    };
    var contracts = $resource('/odata/contracts');
    contracts.query();
});

Dargah.controller('ContractSignController', function ($scope, $http) {
    $scope.model = {};
    $scope.sign = function () {
        $http({ method: 'POST', url: '/Contract/GetContractSignContext' });
    };
});
